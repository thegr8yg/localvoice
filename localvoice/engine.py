"""Offline speech recognition with NVIDIA NeMo models (Parakeet / Canary) or Whisper, via ONNX Runtime.

Models are downloaded once from Hugging Face into the local cache; onnx-asr checks
that cache first, so after the first run everything works with no network.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

import numpy as np

log = logging.getLogger(__name__)

# Most NeMo/Whisper ONNX exports handle up to ~20-30 s per call; longer audio is split with Silero VAD.
MAX_CHUNK_SECONDS = 20.0
SUPPORTED_RATES = (8000, 11025, 16000, 22050, 24000, 32000, 44100, 48000)


@dataclass(frozen=True)
class ModelSpec:
    onnx_asr_name: str
    description: str
    cpu_quantization: str | None = "int8"
    gpu_quantization: str | None = None
    takes_language: bool = False


MODELS: dict[str, ModelSpec] = {
    "parakeet-v2": ModelSpec(
        "nemo-parakeet-tdt-0.6b-v2",
        "NVIDIA Parakeet TDT 0.6B v2 - English, most accurate, punctuated (default)",
    ),
    "parakeet-v3": ModelSpec(
        "nemo-parakeet-tdt-0.6b-v3",
        "NVIDIA Parakeet TDT 0.6B v3 - 25 European languages, auto-detected",
    ),
    "canary-1b-v2": ModelSpec(
        "nemo-canary-1b-v2",
        "NVIDIA Canary 1B v2 - 25 languages, slower, set 'language' in config",
        takes_language=True,
    ),
    "whisper-small": ModelSpec(
        "onnx-community/whisper-small",
        "OpenAI Whisper small - 99 languages, slower and less accurate than Parakeet",
        cpu_quantization=None,
        takes_language=True,
    ),
    "whisper-base": ModelSpec(
        "whisper-base",
        "OpenAI Whisper base - tiny and fast, lowest accuracy",
        cpu_quantization=None,
        takes_language=True,
    ),
}

_DEVICE_PROVIDERS = {
    "cuda": "CUDAExecutionProvider",
    "directml": "DmlExecutionProvider",
    "cpu": "CPUExecutionProvider",
}


def pick_providers(device: str = "auto") -> list[str]:
    import onnxruntime as ort

    preload = getattr(ort, "preload_dlls", None)  # loads pip-installed CUDA/cuDNN DLLs (onnxruntime-gpu >= 1.21)
    if preload and "CUDAExecutionProvider" in ort.get_available_providers():
        try:
            preload()
        except Exception as e:  # noqa: BLE001
            log.warning("Could not preload CUDA DLLs: %s", e)
    available = ort.get_available_providers()
    order = ["cuda", "directml", "cpu"] if device == "auto" else [device, "cpu"]
    for dev in order:
        prov = _DEVICE_PROVIDERS.get(dev)
        if prov is None:
            raise ValueError(f"Unknown device {device!r}; use auto, cuda, directml or cpu")
        if prov in available:
            if dev != device and device != "auto":
                log.warning("%s is not available in this onnxruntime build; falling back to CPU", device)
            return [prov] if prov == "CPUExecutionProvider" else [prov, "CPUExecutionProvider"]
    return ["CPUExecutionProvider"]


class Engine:
    def __init__(self, model: str = "parakeet-v2", device: str = "auto", language: str | None = None):
        if model not in MODELS:
            raise ValueError(f"Unknown model {model!r}. Choose from: {', '.join(MODELS)}")
        self.name = model
        self.spec = MODELS[model]
        self.device = device
        self.language = language
        self.providers: list[str] = []
        self._asr = None
        self._vad_asr = None
        self._ready = threading.Event()
        self._error: BaseException | None = None
        self._lock = threading.Lock()

    @property
    def on_gpu(self) -> bool:
        return bool(self.providers) and self.providers[0] != "CPUExecutionProvider"

    def load(self) -> None:
        try:
            import onnx_asr

            self.providers = pick_providers(self.device)
            quant = self.spec.gpu_quantization if self.on_gpu else self.spec.cpu_quantization
            log.info("Loading %s (%s, quantization=%s) on %s", self.name, self.spec.onnx_asr_name, quant,
                     self.providers[0])
            self._asr = onnx_asr.load_model(self.spec.onnx_asr_name, quantization=quant, providers=self.providers)
            self._transcribe(np.zeros(16000, dtype=np.float32), 16000)  # warm up kernels
            log.info("Model ready")
        except BaseException as e:
            self._error = e
            log.exception("Failed to load model")
            raise
        finally:
            self._ready.set()

    def load_async(self) -> threading.Thread:
        t = threading.Thread(target=self._safe_load, name="model-load", daemon=True)
        t.start()
        return t

    def _safe_load(self) -> None:
        try:
            self.load()
        except BaseException:  # noqa: BLE001 - already logged, surfaced via wait_ready()
            pass

    def wait_ready(self, timeout: float | None = None) -> bool:
        ok = self._ready.wait(timeout)
        if self._error:
            raise RuntimeError(f"Model failed to load: {self._error}") from self._error
        return ok

    @property
    def ready(self) -> bool:
        return self._ready.is_set() and self._error is None

    def _kwargs(self) -> dict:
        if self.spec.takes_language and self.language:
            return {"language": self.language}
        return {}

    def _get_vad_asr(self):
        if self._vad_asr is None:
            import onnx_asr

            vad = onnx_asr.load_vad("silero", providers=["CPUExecutionProvider"])
            self._vad_asr = self._asr.with_vad(vad)
        return self._vad_asr

    def _transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        audio = np.ascontiguousarray(audio, dtype=np.float32)
        if sample_rate not in SUPPORTED_RATES:
            audio, sample_rate = resample(audio, sample_rate, 16000), 16000
        with self._lock:
            if len(audio) / sample_rate <= MAX_CHUNK_SECONDS:
                return self._asr.recognize(audio, sample_rate=sample_rate, **self._kwargs())
            segments = self._get_vad_asr().recognize(audio, sample_rate=sample_rate, **self._kwargs())
            return " ".join(seg.text.strip() for seg in segments if seg.text.strip())

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        self.wait_ready()
        if audio.size == 0:
            return ""
        return self._transcribe(audio, sample_rate)


def resample(audio: np.ndarray, src: int, dst: int) -> np.ndarray:
    if src == dst or audio.size == 0:
        return audio
    n = int(round(len(audio) * dst / src))
    x_old = np.linspace(0.0, 1.0, num=len(audio), endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=n, endpoint=False)
    return np.interp(x_new, x_old, audio).astype(np.float32)
