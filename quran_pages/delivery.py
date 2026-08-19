"""Deliver the day's pages: copy to the Desktop and/or send via wacli (WhatsApp)."""

from __future__ import annotations

import datetime
import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

from .config import PAGE_COUNT, Config, log_file
from .downloader import ensure_page

_WACLI_TIMEOUT_SECONDS = 180

# keep child processes windowless when running under pythonw.exe (Windows only)
NO_WINDOW = 0x08000000 if platform.system() == "Windows" else 0  # CREATE_NO_WINDOW


def desktop_dir() -> Path:
    if platform.system() == "Windows":
        try:  # honor a relocated Desktop (e.g. OneDrive folder redirection)
            import winreg

            key = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as handle:
                value, _ = winreg.QueryValueEx(handle, "Desktop")
            return Path(os.path.expandvars(value))
        except (OSError, ImportError):
            pass
    return Path.home() / "Desktop"


def _wacli_search_dirs() -> List[Path]:
    """Common install dirs, for schedulers that hand us a bare-bones PATH."""
    home = Path.home()
    if platform.system() == "Windows":
        local_app_data = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        candidates = [
            local_app_data / "Microsoft" / "WinGet" / "Links",  # winget
            home / "scoop" / "shims",  # scoop
            Path(os.environ.get("ChocolateyInstall", r"C:\ProgramData\chocolatey")) / "bin",
            local_app_data / "Programs" / "wacli",
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "wacli",
            home / "go" / "bin",
            home / "bin",
        ]
    else:
        candidates = [
            Path("/opt/homebrew/bin"),  # Apple silicon Homebrew — not on launchd's PATH
            Path("/usr/local/bin"),
            Path("/opt/local/bin"),
            home / ".local" / "bin",
            home / "go" / "bin",
            home / "bin",
        ]
    return candidates


def wacli_path(configured: str = "") -> Optional[str]:
    """Locate the wacli executable.

    Scheduled runs (launchd, Task Scheduler) inherit a minimal PATH that omits
    Homebrew and other user install dirs, so a plain which() lookup fails there
    even though the app finds wacli fine when launched from a shell. Prefer the
    absolute path saved when the GUI detected it, then PATH, then known dirs.
    """
    name = "wacli.exe" if platform.system() == "Windows" else "wacli"
    if configured:
        resolved = shutil.which(configured) or (
            configured if os.access(configured, os.X_OK) else None
        )
        if resolved:
            return resolved
    found = shutil.which(name)
    if found:
        return found
    for directory in _wacli_search_dirs():
        candidate = directory / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def open_image(path: Path) -> None:
    """Open an image in the platform's default viewer."""
    system = platform.system()
    if system == "Darwin":
        subprocess.run(["open", str(path)], check=True)
    elif system == "Windows":
        os.startfile(str(path))  # noqa — Windows-only API
    else:
        subprocess.run(["xdg-open", str(path)], check=True)


def send_via_wacli(image: Path, number: str, caption: str, configured: str = "") -> None:
    executable = wacli_path(configured)
    if executable is None:
        searched = ", ".join(str(d) for d in _wacli_search_dirs())
        raise RuntimeError(f"wacli executable not found (searched PATH and {searched})")
    result = subprocess.run(
        [executable, "send", "file", "--to", number, "--file", str(image), "--caption", caption],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=_WACLI_TIMEOUT_SECONDS,
        creationflags=NO_WINDOW,
    )
    if result.returncode != 0:
        raise RuntimeError(f"wacli failed: {(result.stderr or result.stdout).strip()}")


def log(message: str) -> None:
    log_file().parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with log_file().open("a", encoding="utf-8") as handle:
        handle.write(f"[{stamp}] {message}\n")


def already_delivered_today(config: Optional[Config] = None) -> bool:
    config = config or Config.load()
    return config.last_delivery_date == datetime.date.today().isoformat()


def deliver_today(config: Optional[Config] = None, force: bool = False) -> List[int]:
    """Deliver the next batch of pages and advance progress; returns pages delivered.

    Pages are delivered sequentially and progress is saved after each one, so a
    mid-batch failure (no network, wacli error) never skips a page. A scheduled
    run that already delivered today is skipped unless force is set, so the task
    firing twice (e.g. a missed-job catch-up) never sends duplicates.
    """
    config = config or Config.load()
    if not force and already_delivered_today(config):
        log(f"skipped: already delivered today (last page {config.last_delivered_page})")
        return []
    delivered: List[int] = []
    for _ in range(max(1, config.pages_per_day)):
        page = config.next_page
        try:
            image = ensure_page(page)
            destinations = []
            display_copy = image
            if config.deliver_to_desktop:
                target_dir = desktop_dir()
                target_dir.mkdir(parents=True, exist_ok=True)
                display_copy = target_dir / image.name
                shutil.copy2(image, display_copy)
                destinations.append("Desktop")
            if config.send_via_wacli and config.wacli_number:
                caption = f"Quran — page {page} of {PAGE_COUNT}"
                send_via_wacli(image, config.wacli_number, caption, config.wacli_path)
                destinations.append(f"WhatsApp {config.wacli_number}")
            if config.open_after_delivery:
                open_image(display_copy)
                destinations.append("opened on screen")
        except Exception as error:
            log(f"page {page}: FAILED — {error}")
            break
        delivered.append(page)
        config.next_page = page % PAGE_COUNT + 1
        config.last_delivered_page = page
        config.last_delivery_date = datetime.date.today().isoformat()
        config.save()
        log(f"page {page}: delivered → {', '.join(destinations) or 'library only'}")
    return delivered
