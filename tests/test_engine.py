import numpy as np
import pytest

from localvoice.engine import MODELS, Engine, pick_providers, resample


def test_resample_length():
    x = np.random.rand(44100).astype(np.float32)
    y = resample(x, 44100, 16000)
    assert len(y) == 16000 and y.dtype == np.float32


def test_unknown_model():
    with pytest.raises(ValueError):
        Engine("nope")


def test_cpu_provider_always_available():
    assert pick_providers("auto")[-1] == "CPUExecutionProvider"
    assert pick_providers("cpu") == ["CPUExecutionProvider"]


def test_catalog_default_is_parakeet():
    assert MODELS["parakeet-v2"].onnx_asr_name == "nemo-parakeet-tdt-0.6b-v2"
