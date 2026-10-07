"""Insert text into whatever window currently has focus."""

from __future__ import annotations

import ctypes
import logging
import time

from . import win32

log = logging.getLogger(__name__)

VK_CONTROL, VK_V, VK_RETURN = 0x11, 0x56, 0x0D


def wait_for_keys_released(vks: set[int], timeout: float = 3.0) -> None:
    """Don't paste while the hotkey's modifiers are still held (Ctrl+Win+V is not Ctrl+V)."""
    deadline = time.monotonic() + timeout
    while any(win32.is_key_down(vk) for vk in vks) and time.monotonic() < deadline:
        time.sleep(0.01)


def _open_clipboard(retries: int = 20) -> None:
    for _ in range(retries):
        if win32.user32.OpenClipboard(None):
            return
        time.sleep(0.01)
    raise OSError("Could not open the clipboard (another app is holding it)")


def get_clipboard_text() -> str | None:
    _open_clipboard()
    try:
        if not win32.user32.IsClipboardFormatAvailable(win32.CF_UNICODETEXT):
            return None
        handle = win32.user32.GetClipboardData(win32.CF_UNICODETEXT)
        if not handle:
            return None
        ptr = win32.kernel32.GlobalLock(handle)
        try:
            return ctypes.wstring_at(ptr)
        finally:
            win32.kernel32.GlobalUnlock(handle)
    finally:
        win32.user32.CloseClipboard()


def set_clipboard_text(text: str) -> None:
    data = ctypes.create_unicode_buffer(text)
    size = ctypes.sizeof(data)
    handle = win32.kernel32.GlobalAlloc(win32.GMEM_MOVEABLE, size)
    if not handle:
        raise MemoryError("GlobalAlloc failed")
    ptr = win32.kernel32.GlobalLock(handle)
    ctypes.memmove(ptr, data, size)
    win32.kernel32.GlobalUnlock(handle)
    _open_clipboard()
    try:
        win32.user32.EmptyClipboard()
        if not win32.user32.SetClipboardData(win32.CF_UNICODETEXT, handle):
            win32.kernel32.GlobalFree(handle)
            raise OSError("SetClipboardData failed")
        # On success the clipboard owns `handle`; we must not free it.
    finally:
        win32.user32.CloseClipboard()


def paste(text: str, restore: bool = True) -> None:
    # Only plain text is saved/restored; images or files on the clipboard are replaced.
    previous = get_clipboard_text() if restore else None
    set_clipboard_text(text)
    win32.send_inputs([
        win32.key_input(VK_CONTROL),
        win32.key_input(VK_V),
        win32.key_input(VK_V, flags=win32.KEYEVENTF_KEYUP),
        win32.key_input(VK_CONTROL, flags=win32.KEYEVENTF_KEYUP),
    ])
    if restore and previous is not None:
        time.sleep(0.25)  # give the target app time to read the clipboard
        set_clipboard_text(previous)


def type_text(text: str) -> None:
    inputs = []
    for ch in text.replace("\r\n", "\n"):
        if ch == "\n":
            inputs += [win32.key_input(VK_RETURN), win32.key_input(VK_RETURN, flags=win32.KEYEVENTF_KEYUP)]
            continue
        units = ch.encode("utf-16-le")
        for i in range(0, len(units), 2):  # surrogate pairs need two events
            code = int.from_bytes(units[i:i + 2], "little")
            inputs += [
                win32.key_input(scan=code, flags=win32.KEYEVENTF_UNICODE),
                win32.key_input(scan=code, flags=win32.KEYEVENTF_UNICODE | win32.KEYEVENTF_KEYUP),
            ]
    win32.send_inputs(inputs)


def insert(text: str, method: str = "clipboard", restore_clipboard: bool = True) -> None:
    if not text:
        return
    if method == "type":
        type_text(text)
    else:
        paste(text, restore=restore_clipboard)
