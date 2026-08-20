"""Download and cache the 604 Quran page images from mp3quran.net."""

from __future__ import annotations

import os
import ssl
import time
import urllib.request
from functools import lru_cache
from pathlib import Path
from typing import Callable, Optional, Tuple

from .config import PAGE_COUNT, Config, pages_dir

PAGE_URL = "https://www.mp3quran.net/api/quran_pages_arabic/{page:03d}.png"
_TIMEOUT_SECONDS = 30
_RETRIES = 3

_CERT_HELP = (
    "could not verify the site's certificate ({error}). "
    "That is this machine's trust store, not a problem with the site. Fix it with any of:\n"
    "  * pip install certifi  — the app picks it up automatically\n"
    "  * Windows: roots are downloaded on demand and Python never triggers that, so "
    "opening https://www.mp3quran.net once in Edge can populate the missing root\n"
    "  * macOS python.org builds: run 'Install Certificates.command' in the Python folder\n"
    "  * behind a company proxy: export its root certificate, then set SSL_CERT_FILE or "
    "put the path in ca_bundle in config.json"
)


@lru_cache(maxsize=1)
def _trust_source() -> Tuple[Optional[str], str]:
    """Where CA certificates come from: (bundle path or None, description).

    Python on Windows only trusts roots already cached in the Windows store —
    it never triggers the on-demand download that browsers do — and python.org
    macOS builds ship with no trust store until their Install Certificates step
    is run. Both surface as CERTIFICATE_VERIFY_FAILED on a perfectly good site,
    so prefer an explicit bundle whenever one is available.
    """
    override = os.environ.get("SSL_CERT_FILE") or Config.load().ca_bundle
    if override and Path(override).is_file():
        return override, f"explicit bundle ({override})"
    try:
        import certifi

        bundle = certifi.where()
        if Path(bundle).is_file():
            return bundle, f"certifi ({bundle})"
    except Exception:  # not installed, or installed but broken
        pass
    return None, "system trust store"


def trust_description() -> str:
    return _trust_source()[1]


def ssl_context() -> ssl.SSLContext:
    bundle, _ = _trust_source()
    return ssl.create_default_context(cafile=bundle)


def _certificate_error(error: BaseException) -> Optional[ssl.SSLCertVerificationError]:
    """urlopen reports the real cause as URLError.reason, so unwrap one level."""
    if isinstance(error, ssl.SSLCertVerificationError):
        return error
    reason = getattr(error, "reason", None)
    return reason if isinstance(reason, ssl.SSLCertVerificationError) else None


def page_path(page: int) -> Path:
    return pages_dir() / f"quran_page_{page:03d}.png"


def is_cached(page: int) -> bool:
    path = page_path(page)
    return path.exists() and path.stat().st_size > 0


def cached_count() -> int:
    return sum(1 for page in range(1, PAGE_COUNT + 1) if is_cached(page))


def ensure_page(page: int) -> Path:
    """Return the local path for a page, downloading it if not cached."""
    if not 1 <= page <= PAGE_COUNT:
        raise ValueError(f"page must be 1..{PAGE_COUNT}, got {page}")
    path = page_path(page)
    if is_cached(page):
        return path

    pages_dir().mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        PAGE_URL.format(page=page), headers={"User-Agent": "QuranPages/1.0"}
    )
    context = ssl_context()
    last_error: Optional[Exception] = None
    for attempt in range(_RETRIES):
        try:
            with urllib.request.urlopen(
                request, timeout=_TIMEOUT_SECONDS, context=context
            ) as response:
                data = response.read()
            if not data:
                raise OSError("empty response")
            partial = path.with_suffix(".part")
            partial.write_bytes(data)
            partial.replace(path)
            return path
        except Exception as error:
            cert_error = _certificate_error(error)
            if cert_error is not None:
                # Retrying cannot help, and the raw message explains nothing.
                raise OSError(_CERT_HELP.format(error=cert_error)) from error
            last_error = error  # network hiccup: back off and retry
            time.sleep(2**attempt)
    raise OSError(f"failed to download page {page}: {last_error}")


def download_all(
    progress: Optional[Callable[[int, int], None]] = None,
    should_stop: Optional[Callable[[], bool]] = None,
) -> int:
    """Download every missing page; returns how many pages the library holds."""
    for page in range(1, PAGE_COUNT + 1):
        if should_stop is not None and should_stop():
            break
        ensure_page(page)
        if progress is not None:
            progress(page, PAGE_COUNT)
    return cached_count()
