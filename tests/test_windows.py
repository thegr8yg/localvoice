"""Checks that only make sense on a real Windows desktop (run in CI on windows-latest)."""

import ctypes
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


def test_input_struct_size_matches_win32():
    from localvoice import win32

    assert ctypes.sizeof(win32.INPUT) == (40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)


def test_clipboard_roundtrip():
    from localvoice import inject

    inject.set_clipboard_text("LocalVoice ✓ 🎤")
    assert inject.get_clipboard_text() == "LocalVoice ✓ 🎤"


def test_hook_installs_and_stops():
    from localvoice.hotkey import KeyboardHook

    hook = KeyboardHook(lambda vk, down: False)
    hook.start()
    hook.stop()


def test_overlay_builds_and_draws():
    from localvoice.overlay import Overlay

    ov = Overlay(level_source=lambda: 0.05)
    for state in ("listening", "locked", "transcribing", "error", "idle"):
        ov._apply(state, "detail")
        ov._draw()
    ov.root.destroy()


def test_tray_icon_builds():
    from localvoice.tray import make_icon

    assert make_icon().size == (64, 64)
