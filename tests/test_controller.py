import numpy as np

from localvoice.config import Config
from localvoice.controller import Controller

RCTRL, LWIN, LCTRL, C = 0xA3, 0x5B, 0xA2, 0x43


class FakeRecorder:
    def __init__(self, seconds=1.0):
        self.seconds = seconds
        self.recording = False
        self.starts = 0

    def start(self):
        self.recording = True
        self.starts += 1

    def stop(self):
        self.recording = False
        return np.zeros(int(16000 * self.seconds), dtype=np.float32), 16000


class FakeEngine:
    ready = True

    def __init__(self, text="hello world."):
        self.text = text
        self.calls = 0

    def transcribe(self, audio, rate):
        self.calls += 1
        return self.text


def make(seconds=1.0, text=" hello world. ", **cfg_kw):
    cfg = Config(**cfg_kw)
    inserted, states, masks = [], [], []
    c = Controller(cfg, FakeEngine(text), FakeRecorder(seconds), insert=inserted.append,
                   on_state=lambda s, d: states.append(s), send_mask=masks.append)
    return c, inserted, states, masks


def drain(c):
    while not c._events.empty():
        c.process_event(*c._events.get())
    while not c._jobs.empty():
        c.transcribe_and_insert(*c._jobs.get())


def test_hold_release_inserts_clean_text():
    c, inserted, states, _ = make()
    c.clock = iter([0.0, 2.0]).__next__
    c.on_key(RCTRL, True)
    c.on_key(RCTRL, False)
    drain(c)
    assert inserted == ["hello world. "]
    assert states == ["listening", "transcribing", "idle"]


def test_short_recording_is_dropped():
    c, inserted, states, _ = make(seconds=0.1, double_tap_lock=False)
    c.clock = iter([0.0, 2.0]).__next__
    c.on_key(RCTRL, True)
    c.on_key(RCTRL, False)
    drain(c)
    assert inserted == [] and c.engine.calls == 0


def test_shortcut_while_holding_cancels():
    c, inserted, states, _ = make()
    c.clock = iter([0.0, 0.5, 1.0]).__next__
    c.on_key(RCTRL, True)
    c.on_key(C, True)  # Right Ctrl + C = copy, not dictation
    c.on_key(RCTRL, False)
    drain(c)
    assert inserted == [] and states[-1] == "idle"


def test_empty_transcript_inserts_nothing():
    c, inserted, _, _ = make(text="   ")
    c.clock = iter([0.0, 2.0]).__next__
    c.on_key(RCTRL, True)
    c.on_key(RCTRL, False)
    drain(c)
    assert inserted == []


def test_win_combo_masks_start_menu():
    c, _, _, masks = make(hotkey="ctrl+win")
    c.clock = iter([0.0, 0.1, 2.0]).__next__
    c.on_key(LCTRL, True)
    c.on_key(LWIN, True)
    c.on_key(LCTRL, False)
    assert c.on_key(LWIN, False) is True  # swallowed and re-sent behind a mask key
    assert masks == [LWIN]
    assert c.on_key(LWIN, False) is False  # nothing pending any more


def test_engine_error_reports_error_state():
    c, inserted, states, _ = make()

    def boom(a, r):
        raise RuntimeError("model exploded")

    c.engine.transcribe = boom
    c.clock = iter([0.0, 2.0]).__next__
    c.on_key(RCTRL, True)
    c.on_key(RCTRL, False)
    drain(c)
    assert states[-1] == "error" and inserted == []
