"""Entry point: GUI by default, --deliver for the OS-scheduled daily run."""

from __future__ import annotations

import argparse
import os
import sys
from typing import Optional, Sequence


def main(argv: Optional[Sequence[str]] = None) -> int:
    if sys.stdout is None or sys.stderr is None:  # pythonw.exe: no console to print to
        devnull = open(os.devnull, "w")
        sys.stdout = sys.stdout or devnull
        sys.stderr = sys.stderr or devnull

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
