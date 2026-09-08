"""Register the daily delivery with the OS scheduler.

Windows → Task Scheduler (schtasks), macOS → launchd (per-user LaunchAgent).
Both run: <python> <project>/run.py --deliver
"""

from __future__ import annotations

import datetime
import os
import platform
import plistlib
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape
from typing import List, Sequence, Tuple

from .config import Config, app_home, frozen

TASK_NAME = "QuranPagesDaily"
_RETRY_SECONDS = 1800  # half an hour between retries of a failed run
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


def _quote(value: str) -> str:
    return f'"{value}"' if " " in value else value


def delivery_command() -> List[str]:
    """Argv the scheduler should run.

    A packaged build has no run.py to point at — and no interpreter beside it —
    so the executable schedules itself. Built windowless, it also means the
    daily run no longer flashes a console window.
    """
    if frozen():
        return [str(Path(sys.executable).resolve()), "--deliver"]
    return [_python_for_scheduling(), str(LAUNCHER), "--deliver"]


def _working_directory() -> str:
    return str(Path(sys.executable).resolve().parent if frozen() else LAUNCHER.parent)


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


def _windows_task_xml(hour: int, minute: int) -> str:
    """Task Scheduler definition for the daily delivery.

    schtasks' plain /TR form inherits defaults that quietly break a daily job on
    a laptop: DisallowStartIfOnBatteries is true (unplugged at delivery time =
    the task never starts) and StartWhenAvailable is false (PC asleep or off at
    the scheduled minute = that day is skipped outright, with no catch-up).
    macOS launchd does neither, which is why the same settings behaved
    differently across the two platforms. Registering from XML lets us turn both
    off and match the mac behaviour.
    """
    start = f"{datetime.date.today().isoformat()}T{hour:02d}:{minute:02d}:00"
    argv = delivery_command()
    command = escape(argv[0])
    arguments = escape(" ".join(_quote(part) for part in argv[1:]))
    working_dir = escape(_working_directory())
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Delivers the day's Quran pages.</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>{start}</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay>
        <DaysInterval>1</DaysInterval>
      </ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT1H</ExecutionTimeLimit>
    <Priority>7</Priority>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{command}</Command>
      <Arguments>{arguments}</Arguments>
      <WorkingDirectory>{working_dir}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def _schtasks(args: list) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["schtasks"] + args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=NO_WINDOW,
    )


def _schedule_windows(hour: int, minute: int) -> None:
    # Task Scheduler reads /XML files as UTF-16.
    xml_file = app_home() / "task.xml"
    app_home().mkdir(parents=True, exist_ok=True)
    xml_file.write_text(_windows_task_xml(hour, minute), encoding="utf-16")

    result = _schtasks(["/Create", "/F", "/TN", TASK_NAME, "/XML", str(xml_file)])
    if result.returncode == 0:
        return

    # Older or locked-down systems can reject /XML; fall back to the simple form
    # so scheduling still works, minus the battery/catch-up settings.
    xml_error = (result.stderr or result.stdout).strip()
    command = " ".join(_quote(part) for part in delivery_command())
    fallback = _schtasks(
        ["/Create", "/F", "/SC", "DAILY", "/TN", TASK_NAME,
         "/ST", f"{hour:02d}:{minute:02d}", "/TR", command]
    )
    if fallback.returncode != 0:
        raise RuntimeError(
            f"{(fallback.stderr or fallback.stdout).strip()} (XML attempt: {xml_error})"
        )


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
        "ProgramArguments": delivery_command(),
        "StartCalendarInterval": {"Hour": hour, "Minute": minute},
        "RunAtLoad": False,
        "EnvironmentVariables": {"PATH": _job_path(_helper_dirs()), "HOME": str(Path.home())},
        "StandardOutPath": log_path,
        "StandardErrorPath": log_path,
        # Relaunch only when the run reports failure, every half hour, until it
        # works. A delivery that misses because the machine had no network at
        # the scheduled minute is retried during the day instead of being lost
        # until tomorrow. --deliver exits non-zero only for a real failure: a
        # successful delivery, and a run correctly skipped because today is
        # already done, both exit zero and stop the cycle.
        "KeepAlive": {"SuccessfulExit": False},
        "ThrottleInterval": _RETRY_SECONDS,
        # A daily background errand should never compete with the user's work.
        "ProcessType": "Background",
        "LowPriorityIO": True,
        "LowPriorityBackgroundIO": True,
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
        _schtasks(["/Delete", "/F", "/TN", TASK_NAME])
    elif system == "macos":
        subprocess.run(
            ["launchctl", "bootout", f"gui/{os.getuid()}/{LAUNCHD_LABEL}"], capture_output=True
        )
        plist = _launchd_plist_path()
        if plist.exists():
            plist.unlink()
