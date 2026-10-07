"""Small always-on-top pill at the bottom of the screen that never takes keyboard focus."""

from __future__ import annotations

import logging
import queue
import sys
import tkinter as tk

log = logging.getLogger(__name__)

W, H = 200, 40
BG = "#16161a"
KEY = "#010203"  # made fully transparent on Windows, so the pill gets rounded ends
COLORS = {"listening": "#ff4d5e", "locked": "#ffb020", "transcribing": "#5aa9ff", "loading": "#8a8a99",
          "error": "#ff4d5e"}
LABELS = {"listening": "Listening", "locked": "Hands-free · tap to finish", "transcribing": "Transcribing…",
          "loading": "Loading model…", "error": "Error"}


class Overlay:
    def __init__(self, level_source=lambda: 0.0):
        self.level_source = level_source
        self._q: queue.Queue = queue.Queue()
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        # The window stays mapped and is shown/hidden by opacity: re-showing a withdrawn window
        # can activate it, which would steal focus from the app we are about to paste into.
        self._hide()
        try:
            self.root.attributes("-transparentcolor", KEY)
            canvas_bg = KEY
        except tk.TclError:  # not Windows
            canvas_bg = BG
        self.root.configure(bg=canvas_bg)
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(f"{W}x{H}+{(sw - W) // 2}+{sh - H - 90}")
        self.canvas = tk.Canvas(self.root, width=W, height=H, bg=canvas_bg, highlightthickness=0)
        self.canvas.pack()
        self.state = "idle"
        self.detail = ""
        self._bars = [0.0] * 14
        self._hide_job = None
        self._make_unfocusable()
        self.root.after(30, self._tick)

    def _make_unfocusable(self) -> None:
        if sys.platform != "win32":
            return
        from . import win32

        self.root.update_idletasks()
        hwnd = win32.user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
        style = win32.user32.GetWindowLongW(hwnd, win32.GWL_EXSTYLE)
        style |= win32.WS_EX_NOACTIVATE | win32.WS_EX_TOOLWINDOW | win32.WS_EX_TOPMOST | win32.WS_EX_TRANSPARENT \
            | win32.WS_EX_LAYERED
        win32.user32.SetWindowLongW(hwnd, win32.GWL_EXSTYLE, style)

    def _show(self) -> None:
        self.root.attributes("-alpha", 0.93)

    def _hide(self) -> None:
        self.root.attributes("-alpha", 0.0)

    # thread-safe
    def set_state(self, state: str, detail: str = "") -> None:
        self._q.put((state, detail))

    def call(self, fn) -> None:
        """Run fn on the Tk thread."""
        self._q.put(("__call__", fn))

    def quit(self) -> None:
        self._q.put(("__quit__", ""))

    def run(self) -> None:
        self.root.mainloop()

    def _tick(self) -> None:
        try:
            while True:
                state, detail = self._q.get_nowait()
                if state == "__quit__":
                    self.root.destroy()
                    return
                if state == "__call__":
                    detail()
                    continue
                self._apply(state, detail)
        except queue.Empty:
            pass
        if self.state in ("listening", "locked"):
            level = min(1.0, self.level_source() * 12)
            self._bars = self._bars[1:] + [level]
        self._draw()
        self.root.after(30, self._tick)

    def _apply(self, state: str, detail: str) -> None:
        self.state, self.detail = state, detail
        if self._hide_job:
            self.root.after_cancel(self._hide_job)
            self._hide_job = None
        if state == "idle":
            self._hide()
            return
        self._bars = [0.0] * len(self._bars)
        self._show()
        if state == "error":
            self._hide_job = self.root.after(2500, self._hide)

    def _draw(self) -> None:
        c = self.canvas
        c.delete("all")
        if self.state == "idle":
            return
        color = COLORS.get(self.state, "#ffffff")
        r = H // 2
        c.create_oval(0, 0, H, H, fill=BG, outline=BG)
        c.create_oval(W - H, 0, W, H, fill=BG, outline=BG)
        c.create_rectangle(r, 0, W - r, H, fill=BG, outline=BG)
        c.create_oval(14, r - 5, 24, r + 5, fill=color, outline=color)
        if self.state in ("listening", "locked"):
            x0, bw = 34, 7
            for i, v in enumerate(self._bars):
                h = 3 + v * (H - 16)
                x = x0 + i * (bw + 2)
                c.create_rectangle(x, r - h / 2, x + bw - 2, r + h / 2, fill=color, outline="")
            if self.state == "locked":
                c.create_text(W - 14, r, text="∞", fill=color, font=("Segoe UI", 11, "bold"), anchor="e")
        else:
            text = LABELS.get(self.state, self.state)
            if self.state == "error" and self.detail:
                text = self.detail[:28]
            c.create_text(32, r, text=text, fill="#e8e8ee", font=("Segoe UI", 10), anchor="w")
