"""System tray icon: status, model picker, start-with-Windows, quit."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable

from PIL import Image, ImageDraw

from . import autostart
from .engine import MODELS

log = logging.getLogger(__name__)

STATE_COLORS = {"idle": (235, 235, 240), "listening": (255, 77, 94), "locked": (255, 176, 32),
                "transcribing": (90, 169, 255), "loading": (138, 138, 153), "error": (255, 77, 94)}


def make_icon(color=(235, 235, 240)) -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((22, 6, 42, 38), radius=10, fill=color)  # mic capsule
    d.arc((14, 18, 50, 46), start=0, end=180, fill=color, width=4)
    d.line((32, 46, 32, 56), fill=color, width=4)
    d.line((22, 57, 42, 57), fill=color, width=4)
    return img


class Tray:
    def __init__(self, app):
        import pystray

        self.app = app
        self._pystray = pystray
        self.status = "Starting..."
        self.icon = pystray.Icon("LocalVoice", make_icon(), "LocalVoice", menu=self._menu())

    def _menu(self):
        ps = self._pystray
        item = ps.MenuItem

        def model_item(key: str):
            return item(MODELS[key].description, self._choose_model(key), radio=True,
                        checked=lambda _i, k=key: self.app.cfg.model == k)

        return ps.Menu(
            item(lambda _i: self.status, None, enabled=False),
            item(lambda _i: f"Hotkey: hold {self.app.cfg.hotkey}", None, enabled=False),
            ps.Menu.SEPARATOR,
            item("Model", ps.Menu(*(model_item(k) for k in MODELS))),
            item("Start with Windows", self._toggle_autostart, checked=lambda _i: autostart.is_enabled()),
            item("Open settings file", self._open_config),
            item("Open log", self._open_log),
            ps.Menu.SEPARATOR,
            item("Quit", lambda: self.app.quit()),
        )

    def _choose_model(self, key: str) -> Callable:
        def handler(_icon, _item):
            self.app.switch_model(key)
        return handler

    def _toggle_autostart(self, _icon, _item):
        try:
            autostart.set_enabled(not autostart.is_enabled())
        except OSError as e:
            log.error("Could not change autostart: %s", e)

    def _open_config(self, _icon, _item):
        os.startfile(self.app.cfg.path())  # type: ignore[attr-defined]

    def _open_log(self, _icon, _item):
        os.startfile(self.app.log_path)  # type: ignore[attr-defined]

    def set_state(self, state: str, detail: str = "") -> None:
        engine = self.app.engine
        where = "GPU" if engine.on_gpu else "CPU"
        self.status = {
            "idle": f"Ready – {engine.name} on {where}",
            "loading": f"Loading {engine.name}… (first run downloads it)",
            "listening": "Listening…",
            "locked": "Listening (hands-free)…",
            "transcribing": "Transcribing…",
            "error": f"Error: {detail}"[:120],
        }.get(state, state)
        try:
            self.icon.icon = make_icon(STATE_COLORS.get(state, STATE_COLORS["idle"]))
            self.icon.title = f"LocalVoice – {self.status}"[:127]
            self.icon.update_menu()
        except Exception:  # noqa: BLE001 - icon not running yet
            pass

    def run_detached(self) -> None:
        self.icon.run_detached()

    def run(self) -> None:
        self.icon.run()

    def stop(self) -> None:
        self.icon.stop()
