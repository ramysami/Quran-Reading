"""Register the daily delivery with the OS scheduler.

Windows → Task Scheduler (schtasks), macOS → launchd (per-user LaunchAgent).
Both run: <python> <project>/run.py --deliver
"""

from __future__ import annotations

import os
import platform
import plistlib
import subprocess
import sys
from pathlib import Path
from typing import Sequence, Tuple

from .config import Config, app_home

TASK_NAME = "QuranPagesDaily"
LAUNCHD_LABEL = "com.quranpages.daily"
LAUNCHER = Path(__file__).resolve().parent.parent / "run.py"


def current_os() -> str:
    return {"Windows": "windows", "Darwin": "macos"}.get(platform.system(), "unsupported")


def os_description() -> str:
    return {
        "windows": "Windows — daily task via Task Scheduler",
        "macos": "macOS — daily task via launchd",
    }.get(current_os(), f"{platform.system()} — scheduling not supported (Windows/macOS only)")


def _python_for_scheduling() -> str:
    """Interpreter for the background job (windowless pythonw.exe on Windows)."""
    executable = Path(sys.executable)
    if current_os() == "windows":
        windowless = executable.with_name("pythonw.exe")
        if windowless.exists():
            return str(windowless)
    return str(executable)


def _parse_time(delivery_time: str) -> Tuple[int, int]:
    try:
        hour_text, minute_text = delivery_time.split(":")
        hour, minute = int(hour_text), int(minute_text)
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError
    except ValueError:
        raise ValueError(f"invalid time {delivery_time!r}; expected HH:MM (24-hour)")
    return hour, minute


NO_WINDOW = 0x08000000 if platform.system() == "Windows" else 0  # CREATE_NO_WINDOW


def _schedule_windows(hour: int, minute: int) -> None:
    command = f'"{_python_for_scheduling()}" "{LAUNCHER}" --deliver'
    result = subprocess.run(
        ["schtasks", "/Create", "/F", "/SC", "DAILY", "/TN", TASK_NAME,
         "/ST", f"{hour:02d}:{minute:02d}", "/TR", command],
        capture_output=True,
        text=True,
        creationflags=NO_WINDOW,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip())


def _launchd_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LAUNCHD_LABEL}.plist"


_STANDARD_PATH_DIRS = (
    "/opt/homebrew/bin",  # Apple silicon Homebrew (wacli lives here)
    "/opt/homebrew/sbin",
    "/usr/local/bin",
    "/opt/local/bin",
    "~/.local/bin",
    "~/go/bin",
    "/usr/bin",
    "/bin",
    "/usr/sbin",
    "/sbin",
)


def _job_path(extra: Sequence[str] = ()) -> str:
    """PATH for the scheduled job.

    launchd starts jobs with a bare /usr/bin:/bin:/usr/sbin:/sbin, which omits
    Homebrew and other user install dirs — so helpers like wacli are invisible
    at delivery time. Build from a fixed, well-known set rather than inheriting
    the launching process's PATH, which can hold transient entries that would
    go stale in a job meant to run for years.
    """
    entries = list(extra) + [str(Path(d).expanduser()) for d in _STANDARD_PATH_DIRS]
    seen, result = set(), []
    for entry in entries:
        if entry and entry not in seen:
            seen.add(entry)
            result.append(entry)
    return os.pathsep.join(result)


def _helper_dirs() -> list:
    """Directory of the saved wacli binary, so an unusual install still works."""
    wacli = Config.load().wacli_path
    return [str(Path(wacli).parent)] if wacli else []


def _schedule_macos(hour: int, minute: int) -> None:
    log_path = str(app_home() / "launchd.log")
    plist = {
        "Label": LAUNCHD_LABEL,
        "ProgramArguments": [_python_for_scheduling(), str(LAUNCHER), "--deliver"],
        "StartCalendarInterval": {"Hour": hour, "Minute": minute},
        "RunAtLoad": False,
        "EnvironmentVariables": {"PATH": _job_path(_helper_dirs()), "HOME": str(Path.home())},
        "StandardOutPath": log_path,
        "StandardErrorPath": log_path,
    }
    app_home().mkdir(parents=True, exist_ok=True)
    path = _launchd_plist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        plistlib.dump(plist, handle)

    domain = f"gui/{os.getuid()}"
    subprocess.run(["launchctl", "bootout", f"{domain}/{LAUNCHD_LABEL}"], capture_output=True)
    result = subprocess.run(
        ["launchctl", "bootstrap", domain, str(path)], capture_output=True, text=True
    )
    if result.returncode != 0:  # fall back to the legacy interface (older macOS)
        subprocess.run(["launchctl", "unload", str(path)], capture_output=True)
        result = subprocess.run(["launchctl", "load", str(path)], capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout).strip())


def schedule_daily(delivery_time: str) -> str:
    """Create or replace the daily task; returns a human-readable confirmation."""
    hour, minute = _parse_time(delivery_time)
    system = current_os()
    if system == "windows":
        _schedule_windows(hour, minute)
        return f"Task Scheduler job '{TASK_NAME}' set for {hour:02d}:{minute:02d} daily."
    if system == "macos":
        _schedule_macos(hour, minute)
        return f"launchd job '{LAUNCHD_LABEL}' set for {hour:02d}:{minute:02d} daily."
    raise RuntimeError(f"unsupported OS: {platform.system()} (Windows and macOS only)")


def unschedule() -> None:
    system = current_os()
    if system == "windows":
        subprocess.run(
            ["schtasks", "/Delete", "/F", "/TN", TASK_NAME],
            capture_output=True,
            creationflags=NO_WINDOW,
        )
    elif system == "macos":
        subprocess.run(
            ["launchctl", "bootout", f"gui/{os.getuid()}/{LAUNCHD_LABEL}"], capture_output=True
        )
        plist = _launchd_plist_path()
        if plist.exists():
            plist.unlink()
