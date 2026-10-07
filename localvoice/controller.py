"""Glues hotkey -> microphone -> model -> text insertion together."""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable

from . import textproc
from .config import Config
from .hotkey import ALT_KEYS, WIN_KEYS, HotkeyMatcher
from .ptt import Action, PushToTalk, State

log = logging.getLogger(__name__)

# An unassigned virtual-key code. Tapping it before Win/Alt is released stops Windows
# from opening the Start menu / focusing the menu bar (same trick AutoHotkey uses).
VK_MASK = 0xE8


class Controller:
    """States reported to `on_state`: loading, idle, listening, locked, transcribing, error."""

    def __init__(
        self,
        cfg: Config,
        engine,
        recorder,
        insert: Callable[[str], None],
        on_state: Callable[[str, str], None] = lambda s, d: None,
        sounds=None,
        send_mask: Callable[[int], None] | None = None,
        wait_released: Callable[[set[int]], None] = lambda vks: None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.cfg = cfg
        self.engine = engine
        self.recorder = recorder
        self.insert = insert
        self.on_state = on_state
        self.sounds = sounds
        self.send_mask = send_mask
        self.wait_released = wait_released
        self.clock = clock
        self.matcher = HotkeyMatcher(cfg.hotkey)
        self.ptt = PushToTalk(double_tap_lock=cfg.double_tap_lock)
        self._mask_pending = False
        self._events: queue.Queue = queue.Queue()
        self._jobs: queue.Queue = queue.Queue()
        self._threads: list[threading.Thread] = []
        self.state = "idle"

    # -- called from the keyboard hook thread; must be fast -------------------------
    def on_key(self, vk: int, down: bool) -> bool:
        ev = self.matcher.feed(vk, down)
        if ev == "press" and self.matcher.vks & (WIN_KEYS | ALT_KEYS):
            self._mask_pending = True
        if ev is not None:
            self._events.put((ev, vk, self.clock()))
        if (self._mask_pending and not down and vk in (WIN_KEYS | ALT_KEYS) and vk in self.matcher.vks
                and self.send_mask is not None):
            if not (self.matcher.held & (WIN_KEYS | ALT_KEYS)):
                self._mask_pending = False
            self.send_mask(vk)  # sends mask key + this key's release as injected input
            return True
        return False

    # -- lifecycle ---------------------------------------------------------------
    def start(self) -> None:
        for target, name in ((self._event_loop, "ptt-events"), (self._job_loop, "transcriber")):
            t = threading.Thread(target=target, name=name, daemon=True)
            t.start()
            self._threads.append(t)
        self._set_state("idle" if getattr(self.engine, "ready", True) else "loading")

    def stop(self) -> None:
        self._events.put(None)
        self._jobs.put(None)

    def set_hotkey(self, spec: str) -> None:
        self.matcher = HotkeyMatcher(spec)
        self.cfg.hotkey = spec

    def _set_state(self, state: str, detail: str = "") -> None:
        self.state = state
        try:
            self.on_state(state, detail)
        except Exception:
            log.exception("on_state callback failed")

    # -- event processing ------------------------------------------------------------
    def process_event(self, ev: str, vk: int, t: float) -> None:
        if ev == "press":
            actions = self.ptt.press(t)
        elif ev == "release":
            actions = self.ptt.release(t)
        else:
            actions = self.ptt.other_key(vk)
        for action in actions:
            self._do(action)
        if self.ptt.state is State.LOCKED and self.state == "listening":
            self._set_state("locked")

    def _event_loop(self) -> None:
        while (item := self._events.get()) is not None:
            try:
                self.process_event(*item)
            except Exception as e:
                log.exception("Error handling key event")
                self._set_state("error", str(e))

    def _do(self, action: Action) -> None:
        if action is Action.START:
            try:
                self.recorder.start()
            except Exception as e:
                log.exception("Microphone error")
                self.ptt.state = State.IDLE
                self._play("error")
                self._set_state("error", f"Microphone: {e}")
                return
            self._play("start")
            self._set_state("listening")
        elif action is Action.STOP:
            if not self.recorder.recording:
                return
            audio, rate = self.recorder.stop()
            self._play("stop")
            if len(audio) / rate < self.cfg.min_duration:
                self._set_state("idle")
                return
            self._set_state("transcribing")
            self._jobs.put((audio, rate))
        elif action is Action.CANCEL:
            if self.recorder.recording:
                self.recorder.stop()
            self._set_state("idle")

    def _play(self, name: str) -> None:
        if self.sounds is not None:
            self.sounds.play(name)

    def _job_loop(self) -> None:
        while (job := self._jobs.get()) is not None:
            self.transcribe_and_insert(*job)

    def transcribe_and_insert(self, audio, rate: int) -> str:
        try:
            if not getattr(self.engine, "ready", True):
                self._set_state("loading", "Waiting for the model to finish loading...")
            t0 = time.perf_counter()
            raw = self.engine.transcribe(audio, rate)
            text = textproc.clean(raw, self.cfg.replacements, self.cfg.add_trailing_space)
            log.info("Transcribed %.1fs of audio in %.0f ms: %r", len(audio) / rate,
                     (time.perf_counter() - t0) * 1000, text)
            if text:
                self.wait_released(self.matcher.vks)
                self.insert(text)
            if self.recorder.recording:  # user already started the next dictation
                self._set_state("locked" if self.ptt.state is State.LOCKED else "listening")
            else:
                self._set_state("idle")
            return text
        except Exception as e:
            log.exception("Transcription failed")
            self._play("error")
            self._set_state("error", str(e))
            return ""
