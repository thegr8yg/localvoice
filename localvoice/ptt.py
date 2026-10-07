"""Push-to-talk state machine, kept free of Windows APIs so it can be unit tested.

Hold the hotkey -> listen; release -> transcribe.
Double-tap the hotkey -> hands-free; press it again to transcribe, or Esc to discard.
Pressing any other key while holding the hotkey cancels (you were using a shortcut).
"""

from __future__ import annotations

from enum import Enum

VK_ESCAPE = 0x1B


class State(Enum):
    IDLE = "idle"
    HOLDING = "holding"
    LOCKED = "locked"


class Action(Enum):
    START = "start"
    STOP = "stop"  # stop and transcribe
    CANCEL = "cancel"  # stop and discard


class PushToTalk:
    def __init__(self, double_tap_lock: bool = True, tap_max: float = 0.3, double_tap_window: float = 0.5):
        self.double_tap_lock = double_tap_lock
        self.tap_max = tap_max
        self.double_tap_window = double_tap_window
        self.state = State.IDLE
        self._press_t = 0.0
        self._last_tap_t: float | None = None
        self._ignore_release = False

    def press(self, t: float) -> list[Action]:
        if self.state is State.IDLE:
            self.state = State.HOLDING
            self._press_t = t
            return [Action.START]
        if self.state is State.LOCKED:
            self.state = State.IDLE
            self._ignore_release = True
            return [Action.STOP]
        return []

    def release(self, t: float) -> list[Action]:
        if self._ignore_release:
            self._ignore_release = False
            return []
        if self.state is not State.HOLDING:
            return []
        if self.double_tap_lock and t - self._press_t < self.tap_max:
            if self._last_tap_t is not None and t - self._last_tap_t < self.double_tap_window:
                self._last_tap_t = None
                self.state = State.LOCKED
                return []
            self._last_tap_t = t
            self.state = State.IDLE
            return [Action.CANCEL]
        self._last_tap_t = None
        self.state = State.IDLE
        return [Action.STOP]

    def other_key(self, vk: int) -> list[Action]:
        if self.state is State.HOLDING:
            self.state = State.IDLE
            self._ignore_release = True
            self._last_tap_t = None
            return [Action.CANCEL]
        if self.state is State.LOCKED and vk == VK_ESCAPE:
            self.state = State.IDLE
            return [Action.CANCEL]
        return []
