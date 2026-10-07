"""User settings, stored as JSON in %APPDATA%\\LocalVoice\\config.json."""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

log = logging.getLogger(__name__)


def app_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    path = base / "LocalVoice"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class Config:
    # Hold this to talk. "+" joins keys that must be held together, e.g. "ctrl+win".
    # See localvoice/hotkey.py for key names, or use "vk:0xNN" for a raw virtual-key code.
    hotkey: str = "right ctrl"
    # Key from engine.MODELS.
    model: str = "parakeet-v2"
    # "auto" (CUDA -> DirectML -> CPU), "cuda", "directml" or "cpu".
    device: str = "auto"
    # Spoken language hint, only used by Whisper and Canary. None = auto/English.
    language: str | None = None
    # Microphone: None for the Windows default, or a device index / name substring.
    input_device: int | str | None = None
    # "clipboard" pastes with Ctrl+V (fast, works everywhere); "type" sends keystrokes.
    paste_method: str = "clipboard"
    restore_clipboard: bool = True
    add_trailing_space: bool = True
    # Tap the hotkey twice quickly to keep listening hands-free; tap again to finish.
    double_tap_lock: bool = True
    sounds: bool = True
    overlay: bool = True
    # Recordings shorter than this (seconds) are treated as accidental and dropped.
    min_duration: float = 0.3
    # Case-insensitive find/replace applied to every transcript, e.g. {"local voice": "LocalVoice"}.
    replacements: dict[str, str] = field(default_factory=dict)

    @classmethod
    def path(cls) -> Path:
        return app_dir() / "config.json"

    @classmethod
    def load(cls, path: Path | None = None) -> Config:
        path = path or cls.path()
        if not path.exists():
            cfg = cls()
            cfg.save(path)
            return cfg
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            log.error("Could not read %s (%s); using defaults", path, e)
            return cls()
        known = {f.name for f in fields(cls)}
        unknown = set(raw) - known
        if unknown:
            log.warning("Ignoring unknown config keys: %s", ", ".join(sorted(unknown)))
        return cls(**{k: v for k, v in raw.items() if k in known})

    def save(self, path: Path | None = None) -> None:
        path = path or self.path()
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
