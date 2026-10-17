# VoxoraStudio — Local multilingual text-to-speech studio

> Türkçe için: [README.tr.md](./README.tr.md)

Chatterbox Multilingual V3 based, PyQt6 text-to-speech production studio. Turkish + multilingual, voice cloning from a reference sample, WAV/MP3 export — runs fully local with CPU/CUDA/DirectML support.

![Üretim stüdyosu](./docs/screenshots/01-uretim.png)

## Features

- **Turkish + multilingual TTS** — Chatterbox V3 engine.
- **Voice cloning** — reference sample (5–20 s recommended) with guide button.
- **Fine control** — language, speed, expression, clarity, creativity, repetition reduction + ready presets.
- **Long-text chunking** — chunk processing with time estimate, char/word/chunk stats.
- **WAV + MP3 export** — 128/192/320 kbps via ffmpeg.
- **Auto device** — CPU/CUDA auto-select + DirectML/ONNX support.
- **Production history** — auto-saved (`outputs/`), undo, bulk delete, move to Recycle Bin.
- **Fast input** — clipboard paste, text cleanup, shortcuts (Ctrl+Enter, Ctrl+S…).
- **Persistent state** — settings (`state/`), production counter, logs.
- **Progress UI** — model-load and generation progress windows, reference-voice warning on first run.

## Quick start

Requirements: Python 3.11 + ffmpeg (for MP3).

```bat
setup.bat          :: checks internet/hardware/ffmpeg, CUDA or CPU fallback
install_check.bat  :: verify installation
run.bat            :: start consoleless (debug: VOXORA_SHOW_CONSOLE=1)
build.bat          :: package dist\VoxoraStudio-0.5.1\ (PyInstaller onedir)
```

Tests: `smoke_test.py` (light/full), `python -m unittest discover -s tests -v`.

For backward compatibility, legacy automation variables `TXTOTTS_SHOW_CONSOLE` and `TXTOTTS_HIDDEN` are still accepted and mapped to `VOXORA_SHOW_CONSOLE` / `VOXORA_HIDDEN`.

## Project structure

```text
app.py               entry point (UI classes in app/ package)
app/                 main_window, dialogs, workers, theme, icons, widgets
tts_engine.py        TTS engine
audio_compressor.py  MP3 export
audio_player.py      preview playback
chunker.py           long-text splitting
config.py            settings (app_state.py, state/)
scripts/             setup_env, gpu_detect, export_onnx
tests/  outputs/  models/  logs/  docs/
```

## Contributing

Small PRs, no model binaries or outputs in commits. See [.github/PULL_REQUEST_TEMPLATE.md](./.github/PULL_REQUEST_TEMPLATE.md).

## License

See [LICENSE](./LICENSE) (pending — to be confirmed).
