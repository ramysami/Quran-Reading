"""Download and cache the 604 Quran page images from mp3quran.net."""

from __future__ import annotations

import time
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from .config import PAGE_COUNT, pages_dir

PAGE_URL = "https://www.mp3quran.net/api/quran_pages_arabic/{page:03d}.png"
_TIMEOUT_SECONDS = 30
_RETRIES = 3


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
    last_error: Optional[Exception] = None
    for attempt in range(_RETRIES):
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
                data = response.read()
            if not data:
                raise OSError("empty response")
            partial = path.with_suffix(".part")
            partial.write_bytes(data)
            partial.replace(path)
            return path
        except Exception as error:  # network hiccups: back off and retry
            last_error = error
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
