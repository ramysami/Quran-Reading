"""Download and cache the 604 Quran page images from mp3quran.net."""

from __future__ import annotations

import os
import platform
import shutil
import ssl
import subprocess
import time
import urllib.request
from functools import lru_cache
from pathlib import Path
from typing import Callable, Optional, Tuple

from .config import PAGE_COUNT, Config, pages_dir

PAGE_URL = "https://www.mp3quran.net/api/quran_pages_arabic/{page:03d}.png"
_TIMEOUT_SECONDS = 30
_RETRIES = 3
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_NO_WINDOW = 0x08000000 if platform.system() == "Windows" else 0  # CREATE_NO_WINDOW

_CERT_HELP = (
    "could not verify the site's certificate ({error}). That is this machine's "
    "certificate trust, not a problem with the site, and the system downloader "
    "could not be used either.\n"
    "  * Windows: roots are fetched from Windows Update on demand and Python never "
    "triggers that — opening https://www.mp3quran.net once in Edge populates the "
    "missing root\n"
    "  * macOS python.org builds: run 'Install Certificates.command' in the Python folder\n"
    "  * behind a company proxy: export its root certificate, then set SSL_CERT_FILE "
    "or put the path in ca_bundle in config.json"
)

# Set once a trust failure sends us to the OS client, so the remaining pages
# skip an attempt that is already known to fail.
_use_os_client = False


class DownloadError(OSError):
    """A failure that retrying will not fix."""


@lru_cache(maxsize=1)
def _trust_source() -> Tuple[Optional[str], str]:
    """Where CA certificates come from: (bundle path or None, description)."""
    override = os.environ.get("SSL_CERT_FILE") or Config.load().ca_bundle
    if override and Path(override).is_file():
        return override, f"explicit bundle ({override})"
    try:  # optional: used when present, never required
        import certifi

        bundle = certifi.where()
        if Path(bundle).is_file():
            return bundle, f"certifi ({bundle})"
    except Exception:
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


@lru_cache(maxsize=1)
def _os_client() -> Optional[Tuple[str, ...]]:
    """Command template for the OS's own HTTPS client, or None if there isn't one.

    Windows validates certificates through CryptoAPI, which downloads missing
    roots from Windows Update on demand. Python's ssl module never triggers
    that, which is why a page Edge loads without complaint can fail here with
    CERTIFICATE_VERIFY_FAILED. Handing the transfer to the OS client keeps the
    app self-contained — nothing to install — while using a trust store the
    system itself keeps up to date. curl ships in System32 on Windows 10+ and
    in /usr/bin on macOS; PowerShell covers anything older.

    '{url}' and '{out}' in the template are substituted per download.
    """
    if platform.system() == "Windows":
        system32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
        curl = str(system32 / "curl.exe") if (system32 / "curl.exe").is_file() else None
    else:
        curl = "/usr/bin/curl" if Path("/usr/bin/curl").is_file() else None
    curl = curl or shutil.which("curl")
    if curl:
        return (curl, "-fsS", "--max-time", str(_TIMEOUT_SECONDS), "-o", "{out}", "{url}")

    if platform.system() == "Windows":
        powershell = shutil.which("powershell") or shutil.which("pwsh")
        if powershell:
            return (
                powershell, "-NoProfile", "-NonInteractive", "-Command",
                "Invoke-WebRequest -Uri '{url}' -OutFile '{out}' -UseBasicParsing",
            )
    return None


def download_client_description() -> str:
    client = _os_client()
    if client is None:
        return "Python only (no system downloader found)"
    name = Path(client[0]).name
    return f"{name} in use" if _use_os_client else f"Python (fallback: {name})"


def _fetch_with_python(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "QuranPages/1.0"})
    with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS, context=ssl_context()) as r:
        return r.read()


def _fetch_with_os(url: str, target: Path) -> None:
    client = _os_client()
    if client is None:
        raise DownloadError("no system downloader available")
    command = [part.format(url=url, out=str(target)) for part in client]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=_TIMEOUT_SECONDS + 30,
        creationflags=_NO_WINDOW,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip() or f"exit code {result.returncode}"
        raise OSError(f"system downloader failed: {detail}")


def _fetch(url: str, target: Path) -> None:
    """Fetch url into target, falling back to the OS client on a trust failure."""
    global _use_os_client
    if _use_os_client:
        _fetch_with_os(url, target)
        return

    try:
        target.write_bytes(_fetch_with_python(url))
        return
    except Exception as error:
        certificate_error = _certificate_error(error)
        if certificate_error is None:
            raise

    if _os_client() is None:
        raise DownloadError(_CERT_HELP.format(error=certificate_error))
    try:
        _fetch_with_os(url, target)
    except Exception as error:
        raise DownloadError(
            f"{_CERT_HELP.format(error=certificate_error)}\n"
            f"  (the system downloader was tried too, and failed: {error})"
        ) from error
    _use_os_client = True


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
    url = PAGE_URL.format(page=page)
    partial = path.with_suffix(".part")
    last_error: Optional[Exception] = None
    for attempt in range(_RETRIES):
        try:
            _fetch(url, partial)
            with partial.open("rb") as handle:
                magic = handle.read(len(_PNG_MAGIC))
            if not magic:
                raise OSError("empty response")
            if magic != _PNG_MAGIC:
                raise OSError(
                    "the server did not return a PNG — a captive portal or proxy "
                    "may be intercepting the request"
                )
            partial.replace(path)
            return path
        except DownloadError:  # retrying cannot help
            partial.unlink(missing_ok=True)
            raise
        except Exception as error:  # network hiccups: back off and retry
            last_error = error
            time.sleep(2**attempt)
    partial.unlink(missing_ok=True)
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
