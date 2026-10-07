"""LocalVoice - hold a key, speak, and the text is typed wherever your cursor is. 100% offline."""

from __future__ import annotations

import argparse
import logging
import sys
import time

from . import __version__
from .config import Config, app_dir
from .engine import MODELS


def _setup_logging(verbose: bool):
    log_path = app_dir() / "localvoice.log"
    handlers: list[logging.Handler] = [logging.FileHandler(log_path, encoding="utf-8")]
    if sys.stderr is not None:  # None under pythonw.exe
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    return log_path


def _read_wav(path: str):
    import wave

    import numpy as np

    with wave.open(path, "rb") as w:
        if w.getsampwidth() != 2:
            raise SystemExit("Only 16-bit PCM WAV files are supported")
        data = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768
        if w.getnchannels() > 1:
            data = data.reshape(-1, w.getnchannels()).mean(axis=1)
        return data, w.getframerate()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="localvoice", description=__doc__)
    p.add_argument("--version", action="version", version=f"localvoice {__version__}")
    p.add_argument("--model", choices=list(MODELS), help="override the model from the config file")
    p.add_argument("--device", choices=["auto", "cuda", "directml", "cpu"], help="override the compute device")
    p.add_argument("--hotkey", help='override the hotkey, e.g. "right ctrl", "ctrl+win", "f13"')
    p.add_argument("--download", action="store_true", help="download the model (and VAD) now, then exit")
    p.add_argument("--transcribe", metavar="WAV", help="transcribe a 16-bit WAV file and print the text")
    p.add_argument("--list-models", action="store_true", help="show available models")
    p.add_argument("--list-devices", action="store_true", help="show microphones")
    p.add_argument("--detect-key", action="store_true", help="print the code of each key you press (try Fn)")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    log_path = _setup_logging(args.verbose)
    cfg = Config.load()
    if args.model:
        cfg.model = args.model
    if args.device:
        cfg.device = args.device
    if args.hotkey:
        cfg.hotkey = args.hotkey

    if args.list_models:
        for key, spec in MODELS.items():
            print(f"{key:15} {spec.description}")
        return 0
    if args.list_devices:
        from .audio import list_devices

        print(list_devices())
        return 0
    if args.detect_key:
        from .hotkey import detect_keys

        detect_keys()
        return 0

    from .engine import Engine

    if args.download or args.transcribe:
        engine = Engine(cfg.model, cfg.device, cfg.language)
        t0 = time.perf_counter()
        engine.load()
        print(f"Loaded {cfg.model} on {engine.providers[0]} in {time.perf_counter() - t0:.1f}s")
        if args.download:
            engine._get_vad_asr()
            print("Models downloaded; LocalVoice can now run fully offline.")
        if args.transcribe:
            audio, rate = _read_wav(args.transcribe)
            t0 = time.perf_counter()
            text = engine.transcribe(audio, rate)
            print(f"[{len(audio) / rate:.1f}s audio in {time.perf_counter() - t0:.2f}s]")
            print(text)
        return 0

    if sys.platform != "win32":
        print("The dictation app runs on Windows only (--transcribe/--download work anywhere).", file=sys.stderr)
        return 1

    from . import win32
    from .app import App

    mutex = win32.single_instance("Local\\LocalVoiceSingleInstance")
    if mutex is None:
        print("LocalVoice is already running (check the system tray).", file=sys.stderr)
        return 1
    App(cfg, log_path).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
