"""Microphone capture. The stream is only open while you are talking."""

from __future__ import annotations

import logging
import threading

import numpy as np

log = logging.getLogger(__name__)

TARGET_RATE = 16000


def list_devices() -> str:
    import sounddevice as sd

    return str(sd.query_devices())


def _resolve_device(device: int | str | None):
    if device is None or isinstance(device, int):
        return device
    import sounddevice as sd

    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0 and device.lower() in d["name"].lower():
            return i
    log.warning("No input device matching %r; using the default", device)
    return None


class Recorder:
    def __init__(self, device: int | str | None = None):
        self.device = _resolve_device(device)
        self._chunks: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._stream = None
        self.sample_rate = TARGET_RATE
        self.level = 0.0  # recent RMS, for the overlay meter

    def _callback(self, indata, frames, time_info, status):
        if status:
            log.debug("audio status: %s", status)
        mono = indata[:, 0].copy()
        with self._lock:
            self._chunks.append(mono)
        self.level = float(np.sqrt(np.mean(mono * mono))) if len(mono) else 0.0

    def start(self) -> None:
        import sounddevice as sd

        with self._lock:
            self._chunks = []
        self.level = 0.0
        # Ask for 16 kHz; if the device refuses, record at its native rate and let the model resample.
        for rate in (TARGET_RATE, None):
            try:
                if rate is None:
                    rate = int(sd.query_devices(self.device, "input")["default_samplerate"])
                self._stream = sd.InputStream(samplerate=rate, channels=1, dtype="float32",
                                              device=self.device, callback=self._callback, blocksize=0)
                self._stream.start()
                self.sample_rate = rate
                return
            except sd.PortAudioError as e:
                log.warning("Could not open microphone at %s Hz: %s", rate, e)
                self._stream = None
        raise RuntimeError("Could not open the microphone")

    def stop(self) -> tuple[np.ndarray, int]:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            finally:
                self._stream = None
        with self._lock:
            audio = np.concatenate(self._chunks) if self._chunks else np.zeros(0, dtype=np.float32)
            self._chunks = []
        self.level = 0.0
        return audio, self.sample_rate

    @property
    def recording(self) -> bool:
        return self._stream is not None
