"""Self-diagnosis: prints everything needed to explain a failed delivery.

Scheduled runs have no console, so when a delivery fails on someone else's
machine there is nothing to look at. This gathers the answers in one place.
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
import urllib.request
from pathlib import Path

from . import delivery, downloader, scheduler
from .config import PAGE_COUNT, Config, app_home, config_file, log_file


def _mask(number: str) -> str:
    return f"…{number[-4:]}" if len(number) > 4 else number or "(not set)"


def _tkinter_status() -> str:
    try:
        import tkinter

        return f"OK (Tk {tkinter.TkVersion})"
    except Exception as error:  # missing _tkinter is the usual cause
        return f"MISSING — {error}"


def _download_status() -> str:
    """Actually fetch from the image host — a broken trust store shows up here."""
    request = urllib.request.Request(
        downloader.PAGE_URL.format(page=1),
        method="HEAD",
        headers={"User-Agent": "QuranPages/1.0"},
    )
    try:
        with urllib.request.urlopen(
            request, timeout=15, context=downloader.ssl_context()
        ) as response:
            return f"OK (HTTP {response.status})"
    except Exception as error:
        return f"FAILED — {error}"


def _task_status() -> str:
    system = scheduler.current_os()
    try:
        if system == "windows":
            result = subprocess.run(
                ["schtasks", "/Query", "/TN", scheduler.TASK_NAME],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                creationflags=scheduler.NO_WINDOW,
            )
            if result.returncode != 0:
                return "NOT REGISTERED — open the app and press 'Save & schedule daily task'"
            return "registered\n" + "\n".join(
                f"    {line}" for line in result.stdout.strip().splitlines()
            )
        if system == "macos":
            result = subprocess.run(
                ["launchctl", "print", f"gui/{os.getuid()}/{scheduler.LAUNCHD_LABEL}"],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                return "NOT REGISTERED — open the app and press 'Save & schedule daily task'"
            wanted = ("state = ", "runs = ", "last exit code")
            lines = [
                line.strip() for line in result.stdout.splitlines()
                if any(key in line for key in wanted)
            ]
            return "registered\n" + "\n".join(f"    {line}" for line in lines)
    except Exception as error:
        return f"could not query — {error}"
    return "unsupported OS"


def report() -> str:
    config = Config.load()
    found = delivery.wacli_path(config.wacli_path)
    lines = [
        "Quran Pages — diagnostics",
        "=" * 46,
        f"OS               : {platform.system()} {platform.release()} ({platform.machine()})",
        f"Python           : {sys.version.split()[0]} — {sys.executable}",
        f"Tkinter          : {_tkinter_status()}",
        f"Settings file    : {config_file()} ({'exists' if config_file().exists() else 'MISSING'})",
        f"Page library     : {downloader.cached_count()} of {PAGE_COUNT} downloaded",
        f"Trust store      : {downloader.trust_description()}",
        f"Image download   : {_download_status()}",
        "",
        f"Delivery time    : {config.delivery_time} ({config.pages_per_day} page/day)",
        f"Next page        : {config.next_page}"
        + (
            f" (last sent {config.last_delivered_page} on {config.last_delivery_date})"
            if config.last_delivered_page
            else " (nothing sent yet)"
        ),
        f"Destinations     : "
        + ", ".join(
            filter(None, [
                "Desktop" if config.deliver_to_desktop else "",
                "open on screen" if config.open_after_delivery else "",
                f"WhatsApp {_mask(config.wacli_number)}" if config.send_via_wacli else "",
            ])
        )
        or "NONE SELECTED",
        "",
        f"wacli (saved)    : {config.wacli_path or '(none)'}",
        f"wacli (resolved) : {found or 'NOT FOUND — install it, or run wacli auth'}",
        f"PATH             : {os.environ.get('PATH', '')}",
        "",
        f"Scheduled task   : {_task_status()}",
        "",
        f"Log file         : {log_file()}",
    ]

    try:
        recent = log_file().read_text(encoding="utf-8").strip().splitlines()[-8:]
        lines += ["Recent deliveries:"] + [f"    {line}" for line in recent]
    except OSError:
        lines += ["Recent deliveries: (no log yet — nothing has run)"]

    return "\n".join(lines)


def main() -> int:
    print(report())
    return 0
