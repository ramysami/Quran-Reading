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

## Download (Windows)

Grab **`QuranPages.exe`** from the
[latest release](https://github.com/ramysami/Quran-Reading/releases/latest).

It is a portable single file: no installation, no Python, nothing else to set
up — everything it needs is inside the executable. Put it wherever you like and
double-click it. Built for **x64**, and runs on ARM64 Windows 11 through
emulation.

- Nothing flashes on screen: the build is windowless, so the daily delivery runs
  without a console window appearing.
- Settings and downloaded pages live in `%APPDATA%\QuranPages`, not next to the
  executable.
- **If you move the .exe**, open it once and press **Save & schedule daily task**
  again — the scheduled job stores the path it was registered with.
- Windows SmartScreen may warn about an unsigned app the first time. Choose
  *More info* → *Run anyway*.

Running from source works on macOS and Windows alike — see below.

## Requirements

Python 3.9+ **with Tkinter**.

- **macOS**: `/usr/bin/python3` (Command Line Tools) works out of the box.
  For Homebrew Python, add Tk with `brew install python-tk`.
- **Windows**: the [python.org](https://www.python.org/downloads/) installer
  includes Tkinter — keep **tcl/tk and IDLE** ticked. Ticking *Add Python to
  PATH* is optional: the launcher falls back to the `py` launcher, which the
  installer always places in `C:\Windows`.

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
python3 run.py --doctor         # print diagnostics (OS, Python, wacli, task, recent log)
```

`--doctor` is the fastest way to explain a delivery that did not arrive — it
reports the resolved wacli path, whether the task is registered, and the last
few log lines in one block (the WhatsApp number is masked).

## How the daily job behaves

On macOS the launch agent is registered with a retry policy rather than a
single daily shot:

| Key | Value | Why |
| --- | --- | --- |
| `KeepAlive` | `{SuccessfulExit: false}` | relaunch only when a run reports failure |
| `ThrottleInterval` | `1800` | wait half an hour between those retries |
| `ProcessType` | `Background` | never compete with foreground work |
| `LowPriorityIO`, `LowPriorityBackgroundIO` | `true` | same, for disk |

So a delivery that fails because the machine had no network at the scheduled
minute is retried through the day instead of being lost until tomorrow. This
works because `--deliver` returns a meaningful exit code: non-zero only for a
real failure, zero both for a successful delivery and for a run correctly
skipped because today is already done — which is what stops the retry cycle.

Two consequences worth knowing:

- **Saving the schedule triggers a delivery attempt.** launchd starts a
  `KeepAlive` job as soon as it is loaded, so pressing *Save & schedule daily
  task* runs one immediately. The same-day guard caps that at one delivery per
  day, so setting up at 20:00 with a 09:00 time still delivers today rather
  than waiting until tomorrow.
- **A permanently failing delivery retries every half hour.** Each attempt is
  logged, so `--doctor` will show what is wrong.

Windows keeps its own equivalents — catch-up for missed runs and no battery
restriction — set through the task XML.

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
  doctor.py               --doctor diagnostics
assets/icon.ico           application icon (generated by tools/make_icon.py)
.github/workflows/        builds and publishes the Windows executable
```

## Building the Windows executable

Tagging a version builds and publishes it automatically:

```bash
git tag v1.0.0 && git push origin v1.0.0
```

The workflow runs PyInstaller on a Windows x64 runner
(`--onefile --noconsole`), smoke-tests the result by running `--doctor` inside
it — which exercises Tkinter, the TLS stack and a real download — and attaches
the executable to a GitHub release. It can also be run manually from the Actions
tab to produce a build artifact without releasing.

The icon is committed; regenerate it with `python3 tools/make_icon.py` only if
the artwork changes.

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

**The scheduled run did nothing, and the log says nothing either.**
Fixed. Two separate problems used to combine here: pressing **Deliver now** to
test marked the day as delivered, so the real scheduled run refused to fire —
and it refused *silently*, because the skip was decided before the code that
writes the log.

Manual and scheduled deliveries are now tracked apart. **Deliver now** always
delivers the next page and never consumes the day's scheduled run; the guard
only stops a *scheduled* task from firing twice in one day, which is what it
was for (a catch-up after the machine wakes must not send duplicates). Every
outcome — delivered, failed, or skipped — is written to `delivery.log`.

**Windows: the task exists but never runs.**
Two Task Scheduler defaults break a daily job, and neither reports an error —
the run simply never happens:

- *Start the task only if the computer is on AC power* is **on** by default, so
  a laptop on battery at delivery time skips the run.
- *Run task as soon as possible after a scheduled start is missed* is **off** by
  default, so a PC that is asleep or shut down at the scheduled minute skips
  that day entirely, with no catch-up.

The app registers its task from an XML definition that turns the first off and
the second on, matching how launchd behaves on macOS. If a locked-down system
rejects the XML, it falls back to a plain task (which is subject to both
defaults again) rather than failing outright.

**Windows: double-clicking the launcher does nothing.**
Run `Quran Pages.bat` from a terminal to see the message it prints. The launcher
checks for Python and Tkinter before starting the windowless process, because
`pythonw.exe` has no console and would otherwise swallow the error, leaving no
sign that anything happened.

**"Failed to remove temporary directory: ..._MEI......" on Windows.**
That warning comes from PyInstaller's bootloader, not from the app: a
single-file build unpacks itself into a temporary folder and removes it on
exit, and the dialog means the removal failed. It appears *after* the delivery
has already happened, so the page was still delivered.

Something was still holding the folder — most often a virus scanner reading
the freshly unpacked files, or a program the app had just launched. The app
now hands images to the shell as a fully detached process, so nothing it
started outlives it holding that folder, and it pauses briefly before exiting.
Leftover `_MEI` folders in `%TEMP%` are harmless and can be deleted.

**Downloads fail with `CERTIFICATE_VERIFY_FAILED`.**
The site's certificate is fine — the machine's certificate trust is incomplete,
and Python is stricter about it than a browser:

- **Windows** fetches root certificates from Windows Update on demand. Python
  trusts only roots already cached in the store and never triggers that fetch,
  so a fresh PC can fail on a page Edge opens without complaint.
- **macOS python.org builds** ship with no trust store until their
  *Install Certificates.command* has been run.

**The app recovers from this by itself — there is nothing to install.** When a
download fails to verify, it hands the transfer to the operating system's own
HTTPS client (`curl.exe` from `System32` on Windows 10+, `/usr/bin/curl` on
macOS, PowerShell on older Windows), which validates against the system trust
chain that Windows keeps up to date. It remembers the switch, so the remaining
pages skip the attempt that is known to fail.

Certificate verification is never disabled. `--doctor` reports which trust store
and which downloader are in use, and whether a real download succeeds.

If you would rather fix the trust store itself, any of these work: open
<https://www.mp3quran.net> once in Edge to populate the missing root; run
*Install Certificates.command* on macOS; or, behind a company proxy that
inspects TLS, export its root certificate and point `ca_bundle` in
`config.json` (or `SSL_CERT_FILE`) at it. If `certifi` happens to be installed
it is used automatically, but it is not required.
