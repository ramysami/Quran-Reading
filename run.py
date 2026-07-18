#!/usr/bin/env python3
"""Launcher for Quran Pages — GUI by default, `run.py --deliver` for the scheduler."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from quran_pages.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
