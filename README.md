# VoxoraStudio — Local multilingual text-to-speech studio

> Türkçe için: [README.tr.md](./README.tr.md)

Chatterbox Multilingual V3 and EMA Lightning based, PyQt6 text-to-speech production studio. Turkish + multilingual, voice cloning from a reference sample; fast single-voice Turkish output with EMA — runs fully local with CPU/CUDA/DirectML support.

![Üretim stüdyosu](./docs/screenshots/01-uretim.png)

## Features

- **Two engines** — Chatterbox V3 (multilingual + cloning) and EMA Lightning (Turkish, single voice, ~34 MB, very fast even on CPU).
- **Voice cloning** — reference sample (5–20 s recommended) with guide button.
- **Fine control** — language, speed, expression, clarity, creativity, repetition reduction + ready presets.
- **Long-text chunking** — chunk processing with time estimate, char/word/chunk stats.
- **WAV + MP3 + OPUS export** — format-aware quality selection via ffmpeg.
- **Auto device** — CPU/CUDA auto-select + DirectML/ONNX support.
- **Production history** — auto-saved (`outputs`), undo, bulk delete, move to Recycle Bin.
- **Fast input** — clipboard paste, text cleanup, shortcuts (Ctrl+Enter, Ctrl+S…).
- **Persistent state** — settings and history in the user data folder, logs separate.
- **Progress UI** — model-load and generation progress windows, reference-voice warning on first run.
- **Installed build** — Windows installer, one-click updates, preserved settings/models.

## Installation (end user)

Run `VoxoraStudio-X.Y.Z-Setup.exe`.

| What | Where | Removed by update? |
|---|---|---|
| Program (EXE + libraries + ffmpeg) | `C:\Program Files\VoxoraStudio` | Yes — replaced in place |
| Settings, history, outputs, logs | `%LOCALAPPDATA%\VoxoraStudio` | **No** |
| Voice models (Chatterbox ~3.2 GB, EMA ~34 MB) | `%USERPROFILE%\.cache\huggingface` | **No** |

The installer creates desktop and Start Menu shortcuts and rewrites them on
every update. Uninstalling keeps settings, outputs and models.

In-app **Settings ▸ Update** uses one of two paths:

- **Fast update (delta, ~90 MB):** if the release carries a delta based on your
  installed version, only changed files download, get verified and are written
  in place. Settings, outputs and models stay untouched.
- **Full installer (364-382 MB):** when no applicable delta exists, the full
  setup downloads and installs silently (same result, bigger download).

Both paths ask for administrator rights once (writing to Program Files) and the
app restarts itself. Model files are not re-downloaded unless they changed.

## Quick start (development)

Requirements: Python 3.11 + ffmpeg (for MP3) + Inno Setup 6 (for the installer).

```bat
setup.bat          :: checks internet/hardware/ffmpeg, CUDA or CPU fallback
install_check.bat  :: verify installation
run.bat            :: start consoleless (debug: VOXORA_SHOW_CONSOLE=1)
build.bat          :: dist\VoxoraStudio-0.6.1\ + dist\installer\VoxoraStudio-0.6.1-Setup.exe
```

Tests: `smoke_test.py` (light/full), `python -m unittest discover -s tests -v`.

For backward compatibility, legacy automation variables `TXTOTTS_SHOW_CONSOLE` and `TXTOTTS_HIDDEN` are still accepted and mapped to `VOXORA_SHOW_CONSOLE` / `VOXORA_HIDDEN`.

Running from source (`python app.py`) still stores data in the repo's `state/`,
`logs/` and `outputs/`; the split only applies to the installed build.

## Project structure

```text
app.py               entry point (UI classes in app/ package)
app/                 main_window, dialogs, workers, theme, icons, widgets
app/paths.py         program / user-data path split
app/updater.py       installer download + silent update
installer/           Inno Setup script (VoxoraStudio.iss)
tts_engine.py        TTS engine
audio_compressor.py  MP3/OPUS export
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
