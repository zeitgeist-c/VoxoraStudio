# VoxoraStudio — local multilingual text-to-speech studio

> Turkish: [README.tr.md](./README.tr.md)

**Type text, pick a voice, hear it. Nothing leaves your machine.**

VoxoraStudio is a PyQt6 text-to-speech studio that runs entirely on your computer. The installer ships with **EMA Lightning** — Turkish, single voice, 48 kHz, fast even on CPU. **Chatterbox** (16 languages plus voice cloning) and **VoxCPM2** (30 languages plus voice design) are downloaded from inside the app, only if you want them.

![VoxoraStudio · Production](./docs/screenshots/01-uretim.png)

---

## Contents

- [What it does](#what-it-does)
- [Screens, one by one](#screens-one-by-one)
  - [1. Production](#1-production)
  - [2. Archive](#2-archive)
  - [3. Tools](#3-tools)
  - [4. Models](#4-models)
  - [5. Settings](#5-settings)
- [Install](#install)
- [Engines](#engines)
- [Where things live](#where-things-live)
- [Build from source](#build-from-source)
- [Limits worth knowing](#limits-worth-knowing)
- [License](#license)

---

## What it does

| Capability | Detail |
|---|---|
| **Three engines, you choose** | EMA ships with the app; Chatterbox and VoxCPM2 download from the Models tab. Nothing downloads behind your back |
| **Voice cloning** | 5–20 second reference sample; Chatterbox and VoxCPM2 |
| **Voice design** | invent a voice from a written description, no reference audio (VoxCPM2 only) |
| **Hardware gate** | VoxCPM2 only on NVIDIA/CUDA machines — otherwise the button is disabled and the card states why |
| **Fine control** | language, speed, expression, clarity, creativity, repetition reduction, plus presets |
| **Long-text chunking** | split, process per chunk, with a duration estimate before you start |
| **WAV + MP3 + OPUS** | format-aware quality selection through ffmpeg |
| **Production archive** | auto-saved, replay, restore the source text, reveal in folder, delete to Recycle Bin |
| **Batch queue** | paste many lines or load a text file, generate them all |
| **Installed build** | Windows installer, self-update, settings and models preserved across updates |

---

## Screens, one by one

### 1. Production

![Production](./docs/screenshots/01-uretim.png)

The default workspace, split into three columns.

**Left — text**
- The text box, with a live counter: characters, words, chunks, estimated duration.
- `Paste` and `Clear`.
- The active configuration strip under the box: engine, language, speed (`0.90x`), pause length (`0.35 s`), voice mode (`Single voice`).

**Right — voice profile and result**
- **Voice Profile** — the active engine card (`EMA Lightning`, *fixed voice, no reference needed*), with `Select`, `Listen`, `Remove`, `Guide`.
- **Result** — the waveform appears here after generation, with `Play`, `Stop`, `WAV`, `MP3`.

**Bottom — batch queue**
- `+ Add Text`, `Load from File`, `Produce All`, `Clear`.
- Each queued line is generated in order; the queue survives a restart.

`Produce Voice` in the top right starts the run. The status bar at the bottom always shows the engine and the device it is using — `READY · Ready · EMA Lightning (cpu)`.

The header also carries a running total (`Total: 0 productions`) so you know how much you have produced without opening the Archive.

### 2. Archive

![Archive](./docs/screenshots/02-arsiv.png)

Every production, newest first.

- Search box and a list of files.
- **Recording Detail** on the right: the summary of the selected production and its actions.
- `Regenerate` — regenerate from the stored text.
- `Restore Text` — put the original text back into the Production box.
- `Play`, `Show in Folder`, `Delete`, `Bulk Delete`.

Deleting moves files to the Recycle Bin rather than destroying them. Each entry keeps its source text, so a regenerated take uses exactly the text that produced the original.

### 3. Tools

![Tools](./docs/screenshots/03-araclar.png)

Two utilities rather than one page.

**Compress (Opus)**
- Source files: WAV, MP3, FLAC, OGG. `Add File`, `Clear List`.
- Bitrate selection — `Normal (48 kbps)` and the higher options.
- `Results` shows what was produced where.

**System info** — engine availability, device, and the hardware facts the app checks before enabling an engine.

Compression runs locally through the bundled ffmpeg; no upload, no re-encoding by a third party.

### 4. Models

![Models](./docs/screenshots/04-modeller.png)

One card per engine, with what it costs and whether it can run here.

| Engine | Size | Languages | State |
|---|---|---|---|
| **EMA Lightning** | 44 MB | 1 (Turkish) | installed with the app |
| **Chatterbox Multilingual** | 3.5 GB | 16, plus voice cloning | not downloaded |
| **VoxCPM2** | 5.2 GB | 30, plus voice design | not published for this machine |

Each card shows a state badge — `Installed (ships with the app)`, `Not downloaded`, `Not published yet` — with `Download` and `Remove`.

VoxCPM2 is gated on hardware: *"Runs only on computers with an NVIDIA graphics card. No NVIDIA graphics card / CUDA found on this computer."* The card says so plainly instead of offering a download that could not run.

The **Model folder** footer shows where weights live, how much space they take (`Used: 33 MB`), free disk space, and `Open folder` / `Refresh`. Installation and uninstallation never touch this folder, so downloaded engines survive updates.

### 5. Settings

![Settings](./docs/screenshots/05-ayarlar.png)

Five sections down the left, each with its own panel.

**Voice**
- Engine, preset, language, and the five dials: expression, creativity, pause, speed, clarity, repetition reduction.
- `Apply` applies the change. Presets (`Narrator` and the others) set a known-good combination so you do not have to tune from scratch.

**Output** — format, quality, output folder.

**Appearance** — theme and layout.

**Update** — check for updates; the update verifies SHA-256 and replaces the program in place while keeping settings, outputs and models.

**Reset** — return settings to defaults. This resets preferences, not your productions.

---

## Install

Run `VoxoraStudio-<version>-Setup.exe` (~180 MB).

| What | Where | Removed by an update? |
|---|---|---|
| Program (EXE + libraries + ffmpeg + EMA model) | `C:\Program Files\VoxoraStudio` | Yes — replaced in place |
| Settings, history, outputs, logs | `%LOCALAPPDATA%\VoxoraStudio` | **No** |
| Downloaded engines and models | `%LOCALAPPDATA%\VoxoraStudio\engines` and `\models` | **No** |

The installer creates desktop and Start Menu shortcuts. Uninstalling keeps your settings, outputs and downloaded models.

## Engines

| Engine | Languages | Voice cloning | Voice design | Hardware |
|---|---|---|---|---|
| **EMA Lightning** | Turkish | no (single fixed voice) | no | CPU, ships with the app |
| **Chatterbox Multilingual** | 16 | yes | no | CPU works; slower on long text |
| **VoxCPM2** | 30 | yes | yes | NVIDIA/CUDA required |

None of them is downloaded without you pressing `Download`. Every card states size and requirement before the download starts.

## Where things live

| What | Where |
|---|---|
| Program | `C:\Program Files\VoxoraStudio` |
| Settings, history, outputs, logs | `%LOCALAPPDATA%\VoxoraStudio` |
| Engines | `%LOCALAPPDATA%\VoxoraStudio\engines` |
| Models | `%LOCALAPPDATA%\VoxoraStudio\models` |
| Updates | `%LOCALAPPDATA%\VoxoraStudio\updates` |

The split exists because the installer replaces the program folder wholesale. User data outside it survives every update.

## Environment variables

| Variable | Effect |
|---|---|
| `VOXORA_SHOW_CONSOLE` | keep the console window visible when the launcher starts |
| `VOXORA_HIDDEN` | start hidden, without a visible window |

`run.bat` also accepts the pre-rename names `TXTOTTS_SHOW_CONSOLE` and `TXTOTTS_HIDDEN` as aliases, so scripts written against the old launcher keep working. The new `VOXORA_*` names win when both are set.

## Build from source

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Smoke test and packaging:

```powershell
.\.venv\Scripts\python.exe smoke_test.py
```

`smoke_test.py` runs the unit tests, critical and local import checks, an environment check and an optional integration run. Packaging produces the installer through the project's build scripts; the version lives in `app/version.py`.

## Limits worth knowing

- EMA Lightning is Turkish only, with one voice. That is the point — it is the fast, always-available path.
- VoxCPM2 cannot be used on an AMD or Intel GPU; the card disables the download instead of pretending otherwise.
- Chatterbox on CPU is slower on long text; chunk progress and a duration estimate are shown before you start.
- Deleting from the archive sends files to the Recycle Bin, so disk space is freed only after the bin is emptied.

## License

MIT — see [LICENSE](./LICENSE).
