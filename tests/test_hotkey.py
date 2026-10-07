import pytest

from localvoice.hotkey import HotkeyMatcher, parse_hotkey

RCTRL, LCTRL, LWIN, A = 0xA3, 0xA2, 0x5B, 0x41


def test_parse():
    assert parse_hotkey("right ctrl") == [{RCTRL}]
    assert parse_hotkey("Ctrl+Win") == [{0x11, LCTRL, RCTRL}, {0x5B, 0x5C}]
    assert parse_hotkey("vk:0xff") == [{0xFF}]
    assert parse_hotkey("f24") == [{0x87}]
    with pytest.raises(ValueError):
        parse_hotkey("hyper")


def test_single_key_ignores_autorepeat():
    m = HotkeyMatcher("right ctrl")
    assert m.feed(RCTRL, True) == "press"
    assert m.feed(RCTRL, True) is None  # key repeat
    assert m.feed(A, True) == "other"
    assert m.feed(A, False) is None
    assert m.feed(RCTRL, False) == "release"
    assert m.feed(LCTRL, True) == "other"


def test_combo():
    m = HotkeyMatcher("ctrl+win")
    assert m.feed(LCTRL, True) is None
    assert m.feed(LWIN, True) == "press"
    assert m.feed(LCTRL, False) == "release"
    assert m.feed(LWIN, False) is None
