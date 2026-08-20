"""Configuration, persistence, and per-user filesystem paths."""

from __future__ import annotations

import json
import os
import platform
from dataclasses import asdict, dataclass, fields
from pathlib import Path

APP_NAME = "QuranPages"
PAGE_COUNT = 604


def app_home() -> Path:
    """Per-user data directory (override with QURAN_PAGES_HOME, e.g. for tests)."""
    override = os.environ.get("QURAN_PAGES_HOME")
    if override:
        return Path(override)
    system = platform.system()
    if system == "Windows":
        base = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
        return base / APP_NAME
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    return Path.home() / ".config" / "quran-pages"


def pages_dir() -> Path:
    return app_home() / "pages"


def config_file() -> Path:
    return app_home() / "config.json"


def log_file() -> Path:
    return app_home() / "delivery.log"


@dataclass
class Config:
    first_run_done: bool = False
    download_mode: str = "daily"  # "all" (whole library up front) or "daily" (on demand)
    pages_per_day: int = 1
    delivery_time: str = "07:00"  # 24-hour HH:MM
    next_page: int = 1  # 1..PAGE_COUNT, wraps around
    last_delivered_page: int = 0  # 0 = nothing sent yet
    last_delivery_date: str = ""  # ISO date of the most recent delivery
    deliver_to_desktop: bool = True
    open_after_delivery: bool = False  # open each page in the default image viewer
    send_via_wacli: bool = False
    wacli_number: str = ""  # E.164, e.g. +201234567890
    wacli_path: str = ""  # absolute path, so scheduled runs find it off-PATH
    ca_bundle: str = ""  # optional CA bundle, for machines with a broken trust store

    @classmethod
    def load(cls) -> "Config":
        try:
            data = json.loads(config_file().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def save(self) -> None:
        app_home().mkdir(parents=True, exist_ok=True)
        config_file().write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
