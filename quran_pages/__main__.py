"""Entry point: GUI by default, --deliver for the OS-scheduled daily run."""

from __future__ import annotations

import argparse
import os
import platform
import sys
import time
from typing import Optional, Sequence

from .config import frozen


def _ensure_output() -> None:
    """Give the CLI somewhere to print when there is no console of our own.

    The packaged build is windowless — that is what stops a console flashing on
    every scheduled run — which leaves sys.stdout as None. Attaching to the
    terminal that launched us keeps --doctor and friends usable, and anything
    started by the scheduler falls through to a null sink instead of crashing
    on the first print().
    """
    if sys.stdout is not None and sys.stderr is not None:
        return
    if platform.system() == "Windows":
        try:
            import ctypes

            if ctypes.windll.kernel32.AttachConsole(-1):  # ATTACH_PARENT_PROCESS
                console = open("CONOUT$", "w", encoding="utf-8", errors="replace")
                sys.stdout = sys.stdout or console
                sys.stderr = sys.stderr or console
                return
        except Exception:
            pass
    sink = open(os.devnull, "w")
    sys.stdout = sys.stdout or sink
    sys.stderr = sys.stderr or sink


def _settle() -> None:
    """Pause before a packaged build removes its extraction directory.

    A single-file build tears that directory down the moment it exits. Doing so
    immediately after handing a file to the shell — or while a virus scanner is
    still reading the freshly extracted files — is what makes the removal fail,
    and the windowed bootloader reports that failure as a dialog box the user
    has to dismiss. A couple of seconds in a background task costs nothing.
    """
    if frozen() and platform.system() == "Windows":
        time.sleep(2)


def main(argv: Optional[Sequence[str]] = None) -> int:
    _ensure_output()

    parser = argparse.ArgumentParser(prog="quran-pages", description="Daily Quran page delivery.")
    parser.add_argument(
        "--deliver", action="store_true",
        help="deliver today's pages and exit (used by the OS scheduler)",
    )
    parser.add_argument(
        "--download-all", action="store_true",
        help="download all 604 pages into the library and exit",
    )
    parser.add_argument(
        "--unschedule", action="store_true",
        help="remove the daily task from the OS scheduler and exit",
    )
    parser.add_argument(
        "--doctor", action="store_true",
        help="print diagnostics (OS, Python, wacli, task status, recent log) and exit",
    )
    args = parser.parse_args(argv)

    if args.doctor:
        from . import doctor

        return doctor.main()

    if args.unschedule:
        from . import scheduler

        scheduler.unschedule()
        print("daily task removed")
        return 0

    if args.deliver:
        from . import delivery

        # Let deliver_today() apply the guard: it logs why it skipped, and a
        # scheduled run has no console for anything printed here to reach.
        pages = delivery.deliver_today(scheduled=True)
        print(f"delivered pages: {pages}" if pages else "nothing delivered — see delivery.log")
        _settle()
        return 0

    if args.download_all:
        from . import downloader

        total = downloader.download_all(
            progress=lambda done, count: print(f"\r{done}/{count}", end="", flush=True)
        )
        print(f"\nlibrary contains {total} pages")
        return 0

    from .gui import App

    App().mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
