# Quran Pages

A small cross-platform desktop app that delivers Quran pages (the 604-page
Madani mushaf images from [mp3quran.net](https://www.mp3quran.net)) to you once
a day — copied onto your Desktop and/or sent to a WhatsApp number via
[wacli](https://github.com/openclaw/wacli).

It detects your OS and registers the daily job with the native scheduler:

| OS      | Scheduler                                          |
| ------- | -------------------------------------------------- |
| macOS   | launchd (`~/Library/LaunchAgents/com.quranpages.daily.plist`) |
| Windows | Task Scheduler (task name `QuranPagesDaily`)       |

## Features

- **First run** asks whether to download all 604 pages up front (≈130 MB,
  delivery then works offline) or fetch only each day's pages on demand.
- Set **pages per day (n)**, the **delivery time** (24-hour), and the **next
  page** to start from.
- Destinations: **Desktop**, **open on screen** (default image viewer), and/or
  **WhatsApp** through your existing saved `wacli` login (auto-detected; the
  option is disabled if wacli isn't installed).
- Progress is saved after every page — a failed download or send never skips a
  page — and wraps from 604 back to 1.
- Standard library only; no packages to install.

## Requirements

Python 3.9+ **with Tkinter**.

- **macOS**: `/usr/bin/python3` (Command Line Tools) works out of the box.
  For Homebrew Python, add Tk with `brew install python-tk`.
- **Windows**: the [python.org](https://www.python.org/downloads/) installer
  includes Tkinter.

For WhatsApp delivery, install [wacli](https://github.com/openclaw/wacli) and
pair it once with `wacli auth`; the app uses that saved session. The absolute
path to `wacli` is saved in the settings when the app detects it, because
scheduled jobs run with a minimal `PATH` that excludes Homebrew — see
Troubleshooting.

## Run

- macOS: double-click `Quran Pages.command` (or `python3 run.py`)
- Windows: double-click `Quran Pages.bat` (or `python run.py`)

Configure the settings, then press **Save & schedule daily task**. Use
**Deliver now** to test a delivery immediately.

### Command line

```
python3 run.py --deliver        # deliver today's batch (what the scheduler runs)
python3 run.py --download-all   # fetch the whole 604-page library
python3 run.py --unschedule     # remove the daily task from the OS scheduler
```

## Data locations

| What            | macOS                                          | Windows                        |
| --------------- | ---------------------------------------------- | ------------------------------ |
| Settings & log  | `~/Library/Application Support/QuranPages`     | `%APPDATA%\QuranPages`         |
| Page library    | `…/QuranPages/pages`                           | `…\QuranPages\pages`           |

Delivered files land on your Desktop as `quran_page_001.png` … `quran_page_604.png`.

## Code layout

```
run.py                    launcher (also the target the OS scheduler invokes)
quran_pages/
  __main__.py             CLI: GUI by default; --deliver / --download-all / --unschedule
  config.py               settings dataclass + per-OS data paths
  downloader.py           page download/cache (retries, atomic writes)
  delivery.py             Desktop copy + wacli send + progress/log
  scheduler.py            OS detection, schtasks / launchd registration
  gui.py                  Tkinter interface (light theme)
```

## Troubleshooting

**"Deliver now" works, but the scheduled delivery doesn't.**
Almost always a `PATH` problem: launchd (macOS) and Task Scheduler (Windows)
start jobs with a minimal environment that omits `/opt/homebrew/bin` and other
user install dirs, so a helper like `wacli` that works in your shell is
invisible to the daily job. The app handles this by saving wacli's absolute
path in the settings, searching the common install dirs, and writing a usable
`PATH` into the scheduled job. If you move or reinstall wacli, open the app and
press **Save & schedule daily task** again to refresh both.

**Check what the daily job actually did:**

```bash
tail -20 ~/Library/Application\ Support/QuranPages/delivery.log
```

Every run appends either `delivered → …` or `FAILED — <reason>`. A failed page
is not skipped: progress only advances after a successful delivery, so the next
run retries the same page.

**Check the job is registered (macOS):**

```bash
launchctl print gui/$(id -u)/com.quranpages.daily | grep -E "state|runs|last exit"
```
