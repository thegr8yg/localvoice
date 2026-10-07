"""Global hotkey detection via a Windows low-level keyboard hook.

About Fn: on almost every PC keyboard the Fn key is handled inside the keyboard's
firmware and never reaches Windows, so no app can bind to it. Run
`localvoice --detect-key` and press Fn: if nothing prints, pick another key
(Right Ctrl is the default; "ctrl+win" matches Wispr Flow on Windows). Some
laptops do report Fn or remap it to a real key such as F24 -- if a code prints,
use it as the hotkey (e.g. "vk:0xff" or "f24").
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from collections.abc import Callable

log = logging.getLogger(__name__)

# Windows virtual-key codes. Left/right variants are what a low-level hook reports.
_KEYS: dict[str, set[int]] = {
    "ctrl": {0x11, 0xA2, 0xA3},
    "left ctrl": {0xA2},
    "right ctrl": {0xA3},
    "shift": {0x10, 0xA0, 0xA1},
    "left shift": {0xA0},
    "right shift": {0xA1},
    "alt": {0x12, 0xA4, 0xA5},
    "left alt": {0xA4},
    "right alt": {0xA5},
    "altgr": {0xA5},
    "win": {0x5B, 0x5C},
    "left win": {0x5B},
    "right win": {0x5C},
    "menu": {0x5D},
    "caps lock": {0x14},
    "scroll lock": {0x91},
    "pause": {0x13},
    "insert": {0x2D},
    "space": {0x20},
    "tab": {0x09},
    "esc": {0x1B},
}
_KEYS.update({f"f{i}": {0x6F + i} for i in range(1, 25)})
_KEYS.update({chr(c).lower(): {c} for c in range(ord("A"), ord("Z") + 1)})
_KEYS.update({str(d): {0x30 + d} for d in range(10)})

WIN_KEYS = {0x5B, 0x5C}
ALT_KEYS = {0x12, 0xA4, 0xA5}


def parse_hotkey(spec: str) -> list[set[int]]:
    """'ctrl+win' -> [{ctrl vks}, {win vks}]. Each group needs one of its keys held."""
    groups: list[set[int]] = []
    for part in spec.lower().split("+"):
        name = " ".join(part.replace("_", " ").replace("-", " ").split())
        name = {"control": "ctrl", "rctrl": "right ctrl", "lctrl": "left ctrl", "windows": "win",
                "ralt": "right alt", "lalt": "left alt", "capslock": "caps lock"}.get(name, name)
        if name.startswith("vk:"):
            groups.append({int(name[3:], 0)})
        elif name in _KEYS:
            groups.append(set(_KEYS[name]))
        else:
            raise ValueError(f"Unknown key {part!r} in hotkey {spec!r}")
    if not groups:
        raise ValueError("Empty hotkey")
    return groups


class HotkeyMatcher:
    """Turns raw key up/down events into hotkey 'press' / 'release' and 'other' key events."""

    def __init__(self, spec: str):
        self.groups = parse_hotkey(spec)
        self.vks = set().union(*self.groups)
        self.held: set[int] = set()
        self.active = False

    def feed(self, vk: int, down: bool) -> str | None:
        if vk not in self.vks:
            return "other" if down else None
        if down:
            self.held.add(vk)
        else:
            self.held.discard(vk)
        now = all(g & self.held for g in self.groups)
        if now and not self.active:
            self.active = True
            return "press"
        if not now and self.active:
            self.active = False
            return "release"
        return None


class KeyboardHook:
    """Runs a WH_KEYBOARD_LL hook on its own thread.

    `callback(vk, down)` is called for every physical (non-injected) key event and
    must return quickly; returning True swallows the event.
    """

    def __init__(self, callback: Callable[[int, bool], bool]):
        self.callback = callback
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._ready = threading.Event()
        self._error: BaseException | None = None

    def start(self) -> None:
        if sys.platform != "win32":
            raise RuntimeError("The keyboard hook only works on Windows")
        self._thread = threading.Thread(target=self._run, name="keyboard-hook", daemon=True)
        self._thread.start()
        self._ready.wait(5)
        if self._error:
            raise self._error

    def stop(self) -> None:
        if self._thread_id:
            from . import win32

            win32.user32.PostThreadMessageW(self._thread_id, win32.WM_QUIT, 0, 0)

    def _run(self) -> None:
        from . import win32

        def proc(n_code, w_param, l_param):
            if n_code == win32.HC_ACTION:
                kb = win32.KBDLLHOOKSTRUCT.from_address(l_param)
                if not kb.flags & win32.LLKHF_INJECTED:
                    down = w_param in (win32.WM_KEYDOWN, win32.WM_SYSKEYDOWN)
                    try:
                        if self.callback(kb.vkCode, down):
                            return 1
                    except Exception:
                        log.exception("Hotkey callback failed")
            return win32.user32.CallNextHookEx(None, n_code, w_param, l_param)

        self._proc = win32.LowLevelKeyboardProc(proc)  # keep a reference alive
        try:
            self._thread_id = win32.kernel32.GetCurrentThreadId()
            hook = win32.user32.SetWindowsHookExW(win32.WH_KEYBOARD_LL, self._proc, None, 0)
            if not hook:
                raise OSError(f"SetWindowsHookExW failed: {win32.get_last_error()}")
        except BaseException as e:
            self._error = e
            self._ready.set()
            return
        self._ready.set()
        msg = win32.MSG()
        while win32.user32.GetMessageW(win32.byref(msg), None, 0, 0) > 0:
            win32.user32.TranslateMessage(win32.byref(msg))
            win32.user32.DispatchMessageW(win32.byref(msg))
        win32.user32.UnhookWindowsHookEx(hook)


def detect_keys() -> None:
    """Print the virtual-key code of every key pressed (Ctrl+C to quit)."""
    names = {}
    for name, vks in _KEYS.items():
        for vk in vks:
            names.setdefault(vk, name)

    def cb(vk: int, down: bool) -> bool:
        if down:
            print(f"vk=0x{vk:02x}  ({names.get(vk, 'unnamed')})  -> hotkey \"{names.get(vk, f'vk:0x{vk:02x}')}\"",
                  flush=True)
        return False

    hook = KeyboardHook(cb)
    hook.start()
    print("Press keys (try Fn). Ctrl+C to quit.")
    try:
        while True:
            time.sleep(0.2)  # a plain Event.wait() can't be interrupted by Ctrl+C on Windows
    except KeyboardInterrupt:
        hook.stop()
