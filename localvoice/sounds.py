"""Short start/stop chimes, generated once and played asynchronously."""

from __future__ import annotations

import io
import logging
import sys
import wave
from pathlib import Path

import numpy as np

from .config import app_dir

log = logging.getLogger(__name__)


def _tone(freqs: list[float], dur: float = 0.06, rate: int = 22050, volume: float = 0.18) -> bytes:
    parts = []
    for f in freqs:
        t = np.arange(int(rate * dur)) / rate
        env = np.minimum(1.0, np.minimum(t, dur - t) / 0.01)  # 10 ms fade in/out, no clicks
        parts.append(np.sin(2 * np.pi * f * t) * env * volume)
    pcm = (np.concatenate(parts) * 32767).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


class Sounds:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled and sys.platform == "win32"
        self._files: dict[str, Path] = {}
        if self.enabled:
            folder = app_dir() / "sounds"
            folder.mkdir(exist_ok=True)
            for name, freqs in {"start": [660, 880], "stop": [880, 660], "error": [300, 220]}.items():
                path = folder / f"{name}.wav"
                if not path.exists():
                    path.write_bytes(_tone(freqs))
                self._files[name] = path

    def play(self, name: str) -> None:
        if not self.enabled or name not in self._files:
            return
        try:
            import winsound

            winsound.PlaySound(str(self._files[name]), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        except Exception as e:  # noqa: BLE001
            log.debug("Could not play sound: %s", e)
