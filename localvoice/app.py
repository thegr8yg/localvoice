"""The running desktop app: keyboard hook + tray icon + overlay + controller."""

from __future__ import annotations

import logging
import threading

from . import inject, win32
from .audio import Recorder
from .config import Config
from .controller import VK_MASK, Controller
from .engine import Engine
from .hotkey import KeyboardHook
from .sounds import Sounds

log = logging.getLogger(__name__)

_EXTENDED_VKS = {0x5B, 0x5C, 0xA3, 0xA5}  # Win keys, right Ctrl, right Alt


def _send_mask(vk: int) -> None:
    ext = win32.KEYEVENTF_EXTENDEDKEY if vk in _EXTENDED_VKS else 0
    win32.send_inputs([
        win32.key_input(VK_MASK),
        win32.key_input(VK_MASK, flags=win32.KEYEVENTF_KEYUP),
        win32.key_input(vk, flags=win32.KEYEVENTF_KEYUP | ext),
    ])


class App:
    def __init__(self, cfg: Config, log_path):
        self.cfg = cfg
        self.log_path = log_path
        self.engine = Engine(cfg.model, cfg.device, cfg.language)
        self.recorder = Recorder(cfg.input_device)
        self.overlay = None
        self.tray = None
        self.controller = Controller(
            cfg,
            self.engine,
            self.recorder,
            insert=lambda text: inject.insert(text, cfg.paste_method, cfg.restore_clipboard),
            on_state=self._on_state,
            sounds=Sounds(cfg.sounds),
            send_mask=_send_mask,
            wait_released=inject.wait_for_keys_released,
        )
        self.hook = KeyboardHook(self.controller.on_key)
        self._quit = threading.Event()

    def _on_state(self, state: str, detail: str = "") -> None:
        if self.overlay is not None:
            self.overlay.set_state(state, detail)
        if self.tray is not None:
            self.tray.set_state(state, detail)

    def _watch_engine(self, engine: Engine) -> None:
        def wait():
            try:
                engine.wait_ready()
            except RuntimeError as e:
                if engine is self.engine:
                    self._on_state("error", str(e))
                return
            if engine is self.engine and self.controller.state in ("loading", "idle"):
                self.controller._set_state("idle")

        threading.Thread(target=wait, name="engine-watch", daemon=True).start()

    def switch_model(self, key: str) -> None:
        if key == self.cfg.model and self.engine.ready:
            return
        log.info("Switching model to %s", key)
        self.cfg.model = key
        self.cfg.save()
        engine = Engine(key, self.cfg.device, self.cfg.language)
        self.engine = engine
        self.controller.engine = engine
        self.controller._set_state("loading")
        engine.load_async()
        self._watch_engine(engine)

    def run(self) -> None:
        from .tray import Tray

        self.tray = Tray(self)
        if self.cfg.overlay:
            from .overlay import Overlay

            self.overlay = Overlay(level_source=lambda: self.recorder.level)

        self.engine.load_async()
        self.controller.start()
        self._watch_engine(self.engine)
        self.hook.start()
        log.info("LocalVoice running. Hold %r to dictate.", self.cfg.hotkey)

        if self.overlay is not None:
            self.tray.run_detached()
            self.overlay.run()  # Tk must own the main thread
        else:
            self.tray.run()

    def quit(self) -> None:
        log.info("Quitting")
        self.hook.stop()
        self.controller.stop()
        if self.tray is not None:
            self.tray.stop()
        if self.overlay is not None:
            self.overlay.quit()
