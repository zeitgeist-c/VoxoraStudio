# VoxoraStudio — Local multilingual text-to-speech studio

> Türkçe için: [README.tr.md](./README.tr.md)

PyQt6 text-to-speech studio that runs entirely on your machine. The installer
ships with the **EMA Lightning** engine (Turkish, single voice, 48 kHz, fast on
CPU); **Chatterbox** (16 languages + voice cloning) and **VoxCPM2** (30
languages + voice design) are downloaded from inside the app only if you want
them.

![Production studio](./docs/screenshots/01-uretim.png)

## Features

- **Three engines, user picks** — EMA ships with the installer; Chatterbox and
  VoxCPM2 are downloaded from the Models tab. Nothing downloads behind your back.
- **Voice cloning** — reference sample (5–20 s recommended); Chatterbox and VoxCPM2.
- **Voice design** — invent a voice from a written description, no reference
  audio needed (VoxCPM2 only).
- **Hardware gate** — VoxCPM2 can only be selected and downloaded on machines
  with an NVIDIA/CUDA GPU; otherwise the button is disabled and the reason is
  shown in the card.
- **Fine control** — language, speed, expression, clarity, creativity,
  repetition reduction + presets.
- **Long-text chunking** — chunk processing with time estimate.
- **WAV + MP3 + OPUS export** — format-aware quality selection via ffmpeg.
- **Production history** — auto-saved, restore, bulk delete, move to Recycle Bin.
- **Installed build** — Windows installer, one-click updates, preserved
  settings and models.

## Installation (end user)

Run `VoxoraStudio-X.Y.Z-Setup.exe` (~180 MB).

| What | Where | Removed by update? |
|---|---|---|
| Program (EXE + libraries + ffmpeg + EMA model) | `C:\Program Files\VoxoraStudio` | Yes — replaced in place |
| Settings, history, outputs, logs | `%LOCALAPPDATA%\VoxoraStudio` | **No** |
| Downloaded engines and models | `%LOCALAPPDATA%\VoxoraStudio\engines` + `\models` | **No** |

The installer creates desktop and Start Menu shortcuts. Uninstalling keeps
settings, outputs and downloaded models.

### Voice engines

| Engine | Size | Languages | Where from |
|---|---|---|---|
| **EMA Lightning** | 44 MB | Turkish | Ships with the installer — no download |
| **Chatterbox Multilingual** | 3.5 GB | 16 | Models ▸ Download |
| **VoxCPM2** | 5.2 GB | 30 + voice design | Models ▸ Download (CUDA only) |

Engine packs (`.vxp`) are unpacked into your user folder; nothing is installed
into the system Python and nothing is written into the program folder. Every
file is verified with SHA-256 and an interrupted download resumes where it
stopped.

### Updates

**Settings ▸ Update** uses one of two paths:

- **Fast update (delta, ~48 MB):** only changed files download.
- **Full installer (~180 MB):** when no applicable delta exists, the full setup
  downloads and installs silently.

Both paths ask for administrator rights once and the app restarts itself.
Downloaded engines and models stay untouched.

## Quick start (development)

Requirements: Python 3.11 + ffmpeg (for MP3) + Inno Setup 6 (for the installer).

```bat
setup.bat          :: checks internet/hardware, creates the venv
install_check.bat  :: verify installation
run.bat            :: start consoleless (debug: VOXORA_SHOW_CONSOLE=1)
build.bat          :: dist\VoxoraStudio-X.Y.Z\ + dist\installer\VoxoraStudio-X.Y.Z-Setup.exe
```

For working on the optional engines: `pip install -r requirements-dev.txt`
(torch, chatterbox-tts, voxcpm). These never enter the frozen package.

Tests: `smoke_test.py`, `python -m pytest -q`.

For backward compatibility, legacy automation variables `TXTOTTS_SHOW_CONSOLE`
and `TXTOTTS_HIDDEN` are still accepted and mapped to `VOXORA_SHOW_CONSOLE` /
`VOXORA_HIDDEN`.

Running from source (`python app.py`) still stores data in the repo's `state/`,
`logs/` and `outputs/`; the split only applies to the installed build.

## Project structure

```text
app.py               entry point
app/main_window.py   main window and pages
app/paths.py         program / user-data / model path split
app/hardware.py      CUDA + GPU + RAM + disk detection (engine gate)
app/engines.py       engine registry: languages, capabilities, size, requirements
app/model_manager.py install state, download/remove flow
app/engine_pack.py   .vxp engine pack: build, verify, install, remove
app/downloader.py    resumable, cancellable, SHA-256 verified downloader
app/ema_onnx.py      EMA Lightning ONNX engine (no torch)
app/voxcpm_engine.py VoxCPM2 engine (CUDA only)
app/first_run.py     first-run wizard
app/updater.py       installer download + silent update
installer/           Inno Setup script (VoxoraStudio.iss)
tts_engine.py        engine router (common surface: numpy)
models/ema-onnx/     bundled EMA weights
assets/engine_packs.json   engine pack version pins
scripts/             setup_env, gpu_detect, delta generation
```

## Contributing

Small PRs, no model binaries or outputs in commits. See [.github/PULL_REQUEST_TEMPLATE.md](./.github/PULL_REQUEST_TEMPLATE.md).

## License

See [LICENSE](./LICENSE) (pending — to be confirmed).

Engine licenses: EMA Lightning (Apache-2.0), Chatterbox (MIT), VoxCPM2
(Apache-2.0). All free for commercial use.
