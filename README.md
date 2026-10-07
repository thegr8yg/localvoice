# LocalVoice

Hold a key, talk, let go, and the text appears wherever your cursor is: Slack, VS Code, the browser, Word, anywhere.
It's a Windows take on Wispr Flow, but **100% offline**. It uses NVIDIA's open
**Parakeet** speech models (the same FastConformer/TDT family as Nemotron ASR) through ONNX Runtime,
on your NVIDIA GPU, any DirectX 12 GPU, or the CPU.

## Quick start

```powershell
git clone https://github.com/thegr8yg/localvoice
cd localvoice
powershell -ExecutionPolicy Bypass -File scripts\install.ps1
```

The installer creates `.venv`, picks the GPU build if `nvidia-smi` exists (DirectML otherwise),
downloads the model once (~600 MB), and adds **LocalVoice** to the Start Menu.

| Do this | Result |
|---|---|
| **Hold Right Ctrl**, speak, release | Text is pasted into the focused app |
| **Double-tap Right Ctrl** | Hands-free mode: keep talking, tap again to finish, `Esc` to discard |
| Hold Right Ctrl and press another key | Treated as a normal shortcut; nothing is recorded |

A small pill at the bottom of the screen shows when it's listening or transcribing. It never takes focus.
Use the tray icon to switch models, turn on *Start with Windows*, open the settings, or quit.

### Why not the Fn key?

On nearly every PC keyboard, **Fn is handled inside the keyboard's firmware and never reaches Windows**,
so no app can use it (macOS is the exception). To check your keyboard, run:

```powershell
.venv\Scripts\python -m localvoice --detect-key
```

Press Fn. If a code prints (some laptops send one, or let you remap Fn/Copilot keys to F13–F24),
put it in the config as `"hotkey": "vk:0x.."` or `"f24"`. Good alternatives:
`"right ctrl"` (the default), `"ctrl+win"` (Wispr Flow's Windows default), `"right alt"`, `"caps lock"`, `"f13"`.

## Models

| Key | Model | Notes |
|---|---|---|
| `parakeet-v2` *(default)* | NVIDIA Parakeet TDT 0.6B v2 | English. Best accuracy, punctuation and capitals. ~50x real time on CPU, much faster on GPU |
| `parakeet-v3` | NVIDIA Parakeet TDT 0.6B v3 | 25 European languages, detects the language automatically |
| `canary-1b-v2` | NVIDIA Canary 1B v2 | 25 languages, slower; set `"language"` |
| `whisper-small` | OpenAI Whisper small | 99 languages; slower and less accurate than Parakeet on English |
| `whisper-base` | OpenAI Whisper base | Tiny and fast, lowest accuracy |

**"An NVIDIA version of Whisper small":** Parakeet is it. It's similar in size to Whisper small/medium, ranks near the top of
the Hugging Face Open ASR leaderboard for English, and is far faster because it isn't autoregressive.

**About Nemotron ASR Streaming:** that's NVIDIA's *cache-aware streaming* Parakeet model. It shows words live
while you're still talking, trading a little accuracy for latency. With hold-to-talk the whole clip is ready when
you let go, and batch Parakeet transcribes a 10 s clip in a fraction of a second on a GPU, so it's the better default.
Live streaming text with Nemotron is the natural next feature (see *Roadmap*).

Models download once from Hugging Face into `%USERPROFILE%\.cache\huggingface`. After that,
LocalVoice reads them from that cache and makes no network calls. Pre-fetch with `python -m localvoice --download`.

## Settings

`%APPDATA%\LocalVoice\config.json` (tray → *Open settings file*, then restart):

```jsonc
{
  "hotkey": "right ctrl",        // "ctrl+win", "f13", "vk:0xff", ...
  "model": "parakeet-v2",
  "device": "auto",              // auto | cuda | directml | cpu
  "language": null,              // only for canary / whisper, e.g. "de"
  "input_device": null,          // mic index or part of its name, see --list-devices
  "paste_method": "clipboard",   // or "type" (sends keystrokes, leaves clipboard untouched)
  "restore_clipboard": true,
  "add_trailing_space": true,
  "double_tap_lock": true,
  "sounds": true,
  "overlay": true,
  "min_duration": 0.3,
  "replacements": { "local voice": "LocalVoice" }
}
```

## Command line

```
python -m localvoice                      # run the app (tray + hotkey)
python -m localvoice --transcribe a.wav   # transcribe a 16-bit WAV (works on Linux/macOS too)
python -m localvoice --download           # fetch the model now
python -m localvoice --list-models | --list-devices | --detect-key
python -m localvoice --model parakeet-v3 --device cpu --hotkey "ctrl+win" -v
```

Logs go to `%APPDATA%\LocalVoice\localvoice.log`.

## How it works

```
keyboard hook (WH_KEYBOARD_LL) ─► push-to-talk state machine ─► mic (sounddevice, 16 kHz, open only while talking)
                                                                     │ release
                                                                     ▼
       paste via clipboard + Ctrl+V ◄── cleanup/replacements ◄── Parakeet on ONNX Runtime (CUDA / DirectML / CPU)
                                                                  (clips > 20 s are split with Silero VAD)
```

| File | Role |
|---|---|
| `localvoice/hotkey.py` | Low-level keyboard hook, hotkey parsing, `--detect-key` |
| `localvoice/ptt.py` | Hold / double-tap / cancel state machine (pure, unit tested) |
| `localvoice/controller.py` | Wires hotkey → recorder → engine → insertion |
| `localvoice/engine.py` | Model catalog, GPU provider selection, transcription via [`onnx-asr`](https://github.com/istupakov/onnx-asr) |
| `localvoice/audio.py` | Microphone capture |
| `localvoice/inject.py` | Clipboard paste / Unicode typing via `SendInput` |
| `localvoice/overlay.py`, `tray.py` | Status pill and tray menu |

## GPU notes

- **NVIDIA:** `pip install -e .[gpu]` installs `onnxruntime-gpu` along with the CUDA 12 and cuDNN 9 runtime from pip,
  so you don't need the CUDA Toolkit. You only need a recent NVIDIA driver.
- **AMD / Intel / other:** `pip install -e .[directml]`.
- Install only one ONNX Runtime flavor. If you switch, `pip uninstall onnxruntime onnxruntime-gpu onnxruntime-directml` first.
- The tray tooltip shows whether the model runs on the GPU or the CPU.

## Development

```
pip install -e .[cpu,dev]
pytest
```

The state machine, hotkey matching, text cleanup, config and controller are tested on any OS.
The Win32 hook, clipboard, overlay and tray only run on Windows.

## Roadmap

- Live streaming transcription with Nemotron ASR Streaming 0.6B, with words showing in the overlay as you speak
- Personal dictionary / hotword boosting
- Optional local LLM cleanup pass (remove "um", reformat lists) via llama.cpp
- Settings window instead of editing JSON
- Single-file `.exe` build (PyInstaller)
