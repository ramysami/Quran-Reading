"""Light-themed Tkinter interface for Quran Pages."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox, ttk

from . import delivery, downloader, scheduler
from .config import PAGE_COUNT, Config

BG = "#F7F6F1"
CARD = "#FFFFFF"
BORDER = "#E5E2D9"
TEXT = "#2B3530"
MUTED = "#7C867F"
ACCENT = "#1B7A43"
ACCENT_DARK = "#146034"


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Quran Pages")
        self.configure(bg=BG, padx=20, pady=16)
        self.resizable(False, False)

        self.settings = Config.load()
        self.wacli = delivery.wacli_path()
        self._events: "queue.Queue[tuple[str, object]]" = queue.Queue()
        self._busy = False

        self._init_style()
        self._build_header()
        self._build_library_card()
        self._build_schedule_card()
        self._build_destinations_card()
        self._build_actions()
        self._refresh_library_status()

        self.after(120, self._poll_events)
        if not self.settings.first_run_done:
            self.after(300, self._show_first_run_dialog)

        # macOS opens Tk windows behind the current app; bring ours to the front
        self.lift()
        self.attributes("-topmost", True)
        self.after(500, lambda: self.attributes("-topmost", False))

    # ------------------------------------------------------------------ style

    def _init_style(self) -> None:
        base = tkfont.nametofont("TkDefaultFont")
        family = base.actual("family")
        self.font_body = (family, 13)
        self.font_small = (family, 11)
        self.font_title = (family, 14, "bold")
        self.font_header = (family, 22, "bold")

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", background=CARD, foreground=TEXT, font=self.font_body)
        style.configure("Card.TLabel", background=CARD)
        style.configure("CardTitle.TLabel", background=CARD, font=self.font_title)
        style.configure("Muted.TLabel", background=CARD, foreground=MUTED, font=self.font_small)
        style.configure("Bg.TLabel", background=BG)
        style.configure("Header.TLabel", background=BG, foreground=ACCENT, font=self.font_header)
        style.configure("Sub.TLabel", background=BG, foreground=MUTED, font=self.font_small)
        style.configure("Status.TLabel", background=BG, foreground=ACCENT_DARK, font=self.font_small)

        style.configure(
            "Accent.TButton",
            background=ACCENT,
            foreground="#FFFFFF",
            borderwidth=0,
            focuscolor=ACCENT,
            padding=(14, 7),
        )
        style.map("Accent.TButton", background=[("active", ACCENT_DARK), ("disabled", "#A9C4B3")])
        style.configure(
            "Plain.TButton",
            background="#EDEBE3",
            foreground=TEXT,
            borderwidth=0,
            focuscolor="#EDEBE3",
            padding=(14, 7),
        )
        style.map("Plain.TButton", background=[("active", "#E0DDD2"), ("disabled", "#F1EFE9")])

        style.configure("Card.TCheckbutton", background=CARD, font=self.font_body)
        style.map("Card.TCheckbutton", background=[("active", CARD)])
        style.configure("TSpinbox", arrowsize=12, padding=3)
        style.configure("TEntry", padding=4)
        style.configure(
            "Green.Horizontal.TProgressbar",
            background=ACCENT,
            troughcolor="#EDEBE3",
            borderwidth=0,
            thickness=8,
        )

    def _card(self) -> tk.Frame:
        frame = tk.Frame(self, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        frame.pack(fill="x", pady=(0, 12))
        inner = tk.Frame(frame, bg=CARD)
        inner.pack(fill="x", padx=16, pady=12)
        return inner

    # ------------------------------------------------------------------ build

    def _build_header(self) -> None:
        header = tk.Frame(self, bg=BG)
        header.pack(fill="x", pady=(0, 12))
        ttk.Label(header, text="Quran Pages", style="Header.TLabel").pack(anchor="w")
        ttk.Label(header, text=scheduler.os_description(), style="Sub.TLabel").pack(anchor="w")

    def _build_library_card(self) -> None:
        card = self._card()
        ttk.Label(card, text="Page library", style="CardTitle.TLabel").pack(anchor="w")
        self.library_label = ttk.Label(card, style="Muted.TLabel")
        self.library_label.pack(anchor="w", pady=(2, 6))
        self.progress = ttk.Progressbar(
            card, style="Green.Horizontal.TProgressbar", maximum=PAGE_COUNT, length=440
        )
        self.progress.pack(fill="x", pady=(0, 8))
        self.download_button = ttk.Button(
            card, text="Download all 604 pages", style="Plain.TButton",
            command=self._start_download_all,
        )
        self.download_button.pack(anchor="w")

    def _build_schedule_card(self) -> None:
        card = self._card()
        ttk.Label(card, text="Daily delivery", style="CardTitle.TLabel").grid(
            row=0, column=0, columnspan=6, sticky="w", pady=(0, 8)
        )

        self.pages_var = tk.StringVar(value=str(self.settings.pages_per_day))
        ttk.Label(card, text="Pages per day", style="Card.TLabel").grid(row=1, column=0, sticky="w")
        ttk.Spinbox(card, from_=1, to=PAGE_COUNT, textvariable=self.pages_var, width=5).grid(
            row=1, column=1, sticky="w", padx=(8, 24)
        )

        hour, minute = self.settings.delivery_time.split(":")
        self.hour_var = tk.StringVar(value=hour)
        self.minute_var = tk.StringVar(value=minute)
        ttk.Label(card, text="Time (24h)", style="Card.TLabel").grid(row=1, column=2, sticky="w")
        ttk.Spinbox(card, from_=0, to=23, format="%02.0f", textvariable=self.hour_var, width=4).grid(
            row=1, column=3, sticky="w", padx=(8, 2)
        )
        ttk.Label(card, text=":", style="Card.TLabel").grid(row=1, column=4)
        ttk.Spinbox(
            card, from_=0, to=59, format="%02.0f", textvariable=self.minute_var, width=4
        ).grid(row=1, column=5, sticky="w", padx=(2, 0))

        self.next_page_var = tk.StringVar(value=str(self.settings.next_page))
        ttk.Label(card, text="Next page", style="Card.TLabel").grid(
            row=2, column=0, sticky="w", pady=(8, 0)
        )
        ttk.Spinbox(card, from_=1, to=PAGE_COUNT, textvariable=self.next_page_var, width=5).grid(
            row=2, column=1, sticky="w", padx=(8, 0), pady=(8, 0)
        )
        ttk.Label(card, text="(where tomorrow's batch starts)", style="Muted.TLabel").grid(
            row=2, column=2, columnspan=4, sticky="w", padx=(8, 0), pady=(8, 0)
        )
        self.last_sent_label = ttk.Label(card, style="Muted.TLabel")
        self.last_sent_label.grid(row=3, column=0, columnspan=6, sticky="w", pady=(8, 0))
        self._refresh_last_sent()

    def _build_destinations_card(self) -> None:
        card = self._card()
        ttk.Label(card, text="Send pages to", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 6))

        self.desktop_var = tk.BooleanVar(value=self.settings.deliver_to_desktop)
        ttk.Checkbutton(
            card, text="Copy to Desktop", variable=self.desktop_var, style="Card.TCheckbutton"
        ).pack(anchor="w")

        self.open_var = tk.BooleanVar(value=self.settings.open_after_delivery)
        ttk.Checkbutton(
            card, text="Open on screen (default image viewer)", variable=self.open_var,
            style="Card.TCheckbutton",
        ).pack(anchor="w", pady=(4, 0))

        self.wacli_var = tk.BooleanVar(value=self.settings.send_via_wacli and bool(self.wacli))
        wacli_check = ttk.Checkbutton(
            card, text="Send via WhatsApp (wacli)", variable=self.wacli_var,
            style="Card.TCheckbutton",
        )
        wacli_check.pack(anchor="w", pady=(4, 0))

        number_row = tk.Frame(card, bg=CARD)
        number_row.pack(anchor="w", fill="x", pady=(4, 0))
        ttk.Label(number_row, text="WhatsApp number", style="Card.TLabel").pack(side="left")
        self.number_var = tk.StringVar(value=self.settings.wacli_number)
        self.number_entry = ttk.Entry(number_row, textvariable=self.number_var, width=22)
        self.number_entry.pack(side="left", padx=(8, 0))

        if self.wacli:
            wacli_note = f"wacli found: {self.wacli} (uses your saved wacli login)"
        else:
            wacli_note = "wacli not found — install it from github.com/openclaw/wacli, run `wacli auth`, then restart this app"
            wacli_check.state(["disabled"])
            self.number_entry.state(["disabled"])
        ttk.Label(card, text=wacli_note, style="Muted.TLabel", wraplength=440).pack(
            anchor="w", pady=(4, 0)
        )

    def _build_actions(self) -> None:
        row = tk.Frame(self, bg=BG)
        row.pack(fill="x", pady=(2, 8))
        self.schedule_button = ttk.Button(
            row, text="Save & schedule daily task", style="Accent.TButton",
            command=self._save_and_schedule,
        )
        self.schedule_button.pack(side="left")
        self.deliver_button = ttk.Button(
            row, text="Deliver now", style="Plain.TButton", command=self._deliver_now
        )
        self.deliver_button.pack(side="left", padx=(10, 0))
        if scheduler.current_os() == "unsupported":
            self.schedule_button.state(["disabled"])

        self.status_label = ttk.Label(self, text="", style="Status.TLabel", wraplength=470)
        self.status_label.pack(anchor="w")

    # -------------------------------------------------------------- first run

    def _show_first_run_dialog(self) -> None:
        dialog = tk.Toplevel(self, bg=BG, padx=24, pady=20)
        dialog.title("Welcome")
        dialog.resizable(False, False)
        dialog.transient(self)

        ttk.Label(dialog, text="As-salamu alaykum!", style="Header.TLabel").pack(anchor="w")
        ttk.Label(
            dialog,
            text="How would you like to get the 604 Quran pages?",
            style="Bg.TLabel",
        ).pack(anchor="w", pady=(6, 14))

        def choose(mode: str) -> None:
            self.settings.download_mode = mode
            self.settings.first_run_done = True
            self.settings.save()
            dialog.destroy()
            if mode == "all":
                self._start_download_all()
            else:
                self._set_status("Pages will be downloaded as needed, each day.")

        ttk.Button(
            dialog, text="Download all 604 pages now", style="Accent.TButton",
            command=lambda: choose("all"),
        ).pack(fill="x")
        ttk.Label(
            dialog, text="≈130 MB once — daily delivery then works offline.", style="Sub.TLabel"
        ).pack(anchor="w", pady=(4, 12))
        ttk.Button(
            dialog, text="Download a few pages each day", style="Plain.TButton",
            command=lambda: choose("daily"),
        ).pack(fill="x")
        ttk.Label(
            dialog, text="Fetches only the day's pages at delivery time.", style="Sub.TLabel"
        ).pack(anchor="w", pady=(4, 0))

        dialog.protocol("WM_DELETE_WINDOW", lambda: choose("daily"))
        dialog.grab_set()

    # ---------------------------------------------------------------- actions

    def _apply_settings(self) -> bool:
        """Validate the form into self.settings and persist it."""
        try:
            pages = int(self.pages_var.get())
            next_page = int(self.next_page_var.get())
            hour = int(self.hour_var.get())
            minute = int(self.minute_var.get())
            if not (1 <= pages <= PAGE_COUNT and 1 <= next_page <= PAGE_COUNT):
                raise ValueError
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError
        except ValueError:
            messagebox.showerror(
                "Invalid settings",
                "Check the numbers: pages and next page must be 1–604, time must be a valid 24-hour time.",
                parent=self,
            )
            return False

        number = self.number_var.get().strip()
        if self.wacli_var.get() and not number:
            messagebox.showerror(
                "Missing number",
                "Enter the WhatsApp number (e.g. +201234567890) or untick WhatsApp delivery.",
                parent=self,
            )
            return False
        if not (self.desktop_var.get() or self.open_var.get() or self.wacli_var.get()):
            messagebox.showerror(
                "No destination",
                "Pick at least one destination: Desktop, open on screen, or WhatsApp.",
                parent=self,
            )
            return False

        self.settings.pages_per_day = pages
        self.settings.next_page = next_page
        self.settings.delivery_time = f"{hour:02d}:{minute:02d}"
        self.settings.deliver_to_desktop = self.desktop_var.get()
        self.settings.open_after_delivery = self.open_var.get()
        self.settings.send_via_wacli = self.wacli_var.get()
        self.settings.wacli_number = number
        if self.wacli:  # remember the absolute path for scheduled runs
            self.settings.wacli_path = self.wacli
        self.settings.save()
        self._refresh_last_sent()
        return True

    def _save_and_schedule(self) -> None:
        if self._busy or not self._apply_settings():
            return
        try:
            message = scheduler.schedule_daily(self.settings.delivery_time)
        except Exception as error:
            messagebox.showerror("Scheduling failed", str(error), parent=self)
            return
        self._set_status(f"{message} Delivering {self.settings.pages_per_day} page(s)/day.")

    def _deliver_now(self) -> None:
        if self._busy or not self._apply_settings():
            return
        self._set_busy(True)
        self._set_status("Delivering…")
        threading.Thread(target=self._deliver_worker, daemon=True).start()

    def _deliver_worker(self) -> None:
        try:
            pages = delivery.deliver_today(force=True)
            if pages:
                self._events.put(("delivered", pages))
            else:
                self._events.put(("error", "Delivery failed — see the log in the app data folder."))
        except Exception as error:
            self._events.put(("error", f"Delivery failed: {error}"))

    def _start_download_all(self) -> None:
        if self._busy:
            return
        self._set_busy(True)
        self._set_status("Downloading pages…")
        threading.Thread(target=self._download_worker, daemon=True).start()

    def _download_worker(self) -> None:
        try:
            downloader.download_all(
                progress=lambda done, total: self._events.put(("progress", done))
            )
            self._events.put(("done", "Library complete — all 604 pages downloaded."))
        except Exception as error:
            self._events.put(("error", f"Download stopped: {error}"))

    # ----------------------------------------------------------------- events

    def _poll_events(self) -> None:
        try:
            while True:
                kind, payload = self._events.get_nowait()
                if kind == "progress":
                    self.progress["value"] = payload
                    self.library_label["text"] = f"{payload} of {PAGE_COUNT} pages processed…"
                elif kind == "delivered":
                    pages = ", ".join(str(p) for p in payload)
                    self._set_busy(False)
                    self._reload_settings()
                    self._set_status(f"Delivered page(s) {pages}.")
                elif kind == "done":
                    self._set_busy(False)
                    self._refresh_library_status()
                    self._set_status(str(payload))
                elif kind == "error":
                    self._set_busy(False)
                    self._refresh_library_status()
                    self._reload_settings()
                    self._set_status(str(payload))
        except queue.Empty:
            pass
        self.after(120, self._poll_events)

    # ---------------------------------------------------------------- helpers

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = ["disabled"] if busy else ["!disabled"]
        for button in (self.download_button, self.deliver_button, self.schedule_button):
            button.state(state)
        if not busy and scheduler.current_os() == "unsupported":
            self.schedule_button.state(["disabled"])

    def _set_status(self, message: str) -> None:
        self.status_label["text"] = message

    def _refresh_library_status(self) -> None:
        cached = downloader.cached_count()
        self.progress["value"] = cached
        self.library_label["text"] = f"{cached} of {PAGE_COUNT} pages downloaded"

    def _refresh_last_sent(self) -> None:
        if self.settings.last_delivered_page:
            text = (
                f"Last sent: page {self.settings.last_delivered_page}"
                f" on {self.settings.last_delivery_date}"
                f" — tomorrow: page {self.settings.next_page}"
            )
        else:
            text = f"Nothing sent yet — first delivery starts at page {self.settings.next_page}"
        self.last_sent_label["text"] = text

    def _reload_settings(self) -> None:
        """Pick up progress written by a worker (next_page advances on delivery)."""
        self.settings = Config.load()
        self.next_page_var.set(str(self.settings.next_page))
        self._refresh_library_status()
        self._refresh_last_sent()
