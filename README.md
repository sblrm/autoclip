<div align="center">

```
   ___         __       ________
  / _ | __ __/ /____  / ___/ (_)____
 / __ |/ // / __/ _ \\ / /__/ / / __/
/_/ |_|\\_,_/\\__/\\___/\\___/_/_/\\__/
```

# AutoClip

**Local video studio for turning long-form footage into reviewed, vertical clips.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![Local processing](https://img.shields.io/badge/processing-local%20only-2f855a.svg)](#privacy-and-local-processing)

Import one video, find promising moments, lock the right subject, approve the tracking preview, then export a 9:16 MP4. Projects, source media, and processing stay on your machine.

</div>

---

## Why AutoClip

AutoClip is a local-first studio for TikTok, Instagram Reels, and YouTube Shorts. It combines transcription, clip discovery, subtitles, face-aware reframing, and FFmpeg export in one browser workflow. The CLI remains available for direct processing and automation.

| Capability | What it does |
| --- | --- |
| Local Web Studio | Opens a browser-based workspace without requiring Node.js or Vite at launch. |
| Durable projects | Copies imported source media into a local project folder so work survives a browser restart. |
| Clip discovery | Uses local transcription plus Ollama analysis or a heuristic fallback to identify candidates. |
| Review-first tracking | Lets you select and lock one face track, inspect its crop path, and approve a preview before export. |
| Vertical output | Produces 1080 x 1920 MP4 clips with optional ASS/SSA karaoke subtitles. |
| Honest hardware status | Separately reports FFmpeg, trackers, models, CPU/GPU runtime, and NVENC readiness. |
| Indonesian and English UI | Starts in Indonesian; switch to English from the Studio and keep that preference locally. |

## Quick start

### 1. Install prerequisites

| Requirement | Needed for | Notes |
| --- | --- | --- |
| Python 3.10+ | AutoClip runtime | Install from [python.org](https://www.python.org/downloads/). |
| FFmpeg | Import, preview, and export | Windows: `winget install FFmpeg`; otherwise use your platform package manager. |
| Ollama | Optional local AI clip analysis | Install from [ollama.com](https://ollama.com/) only when you want LLM analysis. |

For Ollama analysis, download a local model after installation:

```powershell
ollama pull llama3
```

### 2. Get AutoClip and run setup

```powershell
git clone <your-repository-url>
cd AutoClip
.\setup.bat
```

macOS and Linux:

```bash
git clone <your-repository-url>
cd AutoClip
bash setup.sh
```

Setup creates `.venv`, installs supported Python packages, and provides Windows launchers. In PowerShell, always include `.\` before a script in the current folder.

### 3. Open Local Web Studio

Windows:

```powershell
.\autoclip-web-studio.bat
```

Or, from an installed AutoClip environment:

```powershell
autoclip web
```

Studio opens at `http://127.0.0.1:8765`. Launching it does not build Vite and does not require Node.js. If launcher cannot find `.venv`, run setup first or use:

```powershell
.\.venv\Scripts\python.exe -m autoclip.cli web
```

## Studio workflow

AutoClip v1 intentionally handles one local project and one resource-heavy job at a time.

1. Open **Home** and resolve only required runtime blockers it shows.
2. Create a project and import one local video or a supported HTTP(S) video URL.
3. Analyze source to generate clip candidates.
4. Trim candidate, set title and subtitle options, then choose one face track.
5. Render a tracking preview. Review crop movement and timeline gaps.
6. Approve preview. Only approved previews can be exported.
7. Export 1080 x 1920 MP4 and download or review it from project history.

Project data is stored under `~/.autoclip/projects/`. Imported source files are copied into their project to keep resume and export reliable.

## Face tracking and framing

AutoClip tracks a selected subject rather than switching automatically to whichever face has highest confidence in a frame.

- Detector creates candidate tracks across clip.
- You select and lock one subject per clip.
- A missed detection becomes a visible gap; it never switches identity.
- During short loss, crop holds its last position, then eases toward center.
- Final export uses saved preview trajectory. Review and approval are required before export.

If tracking is unavailable, Studio reports exact missing dependency or model. It does not silently replace subject tracking with an unreported center crop.

## CPU, GPU, and NVENC

CPU mode is valid and fully supported. In **Auto** mode, AutoClip uses a verified CPU tracker and `libx264` when GPU evidence is unavailable.

GPU selection is strict: it requires a live face-tracker inference check and a real FFmpeg encoder smoke test. Selecting GPU or NVENC never silently falls back to CPU.

| Platform | Recommended path | Readiness requirement |
| --- | --- | --- |
| Windows with NVIDIA GPU | YuNet CUDA | PyTorch CUDA, ONNX Runtime CUDA, YuNet model, live `CUDAExecutionProvider` inference, and `h264_nvenc` smoke output. |
| Ubuntu with NVIDIA GPU | MediaPipe GPU | Successful live MediaPipe VIDEO inference, then same preview and export review. |
| CPU-only system | MediaPipe or YuNet CPU | Ready CPU tracker and `libx264`; GPU status explains why unavailable. |

Open **Performance** in Studio and choose **Setup GPU tracking** to install supported components through fixed local repair plans. For a Windows RTX 5070, do not install NVIDIA CUDA Toolkit only for AutoClip when PyTorch CUDA already works. Recheck runtime after each requested install.

FFmpeg needs more than an `h264_nvenc` entry in its encoder list: AutoClip tests a real encode. If NVENC cannot initialize, Auto uses `libx264`; explicitly selected NVENC returns a clear error instead of producing a misleading export.

### Optional tracking engines

| Engine | Best use | Notes |
| --- | --- | --- |
| MediaPipe | Portable CPU tracking; Ubuntu GPU when live delegate works | Uses video timestamps for clip tracking. |
| YuNet | Default Windows CUDA path | Small, fast detector with MIT-licensed model assets. |
| InsightFace SCRFD | Optional higher-capacity detector | Research-only/non-commercial model-pack terms require acknowledgement before download. |
| RetinaFace | Optional alternative detector | Research-only/non-commercial model-pack terms require acknowledgement before download. |

AutoClip performs face detection only. It does not create face-recognition embeddings or send faces to cloud services.

## CLI

CLI stays available for direct pipelines.

```powershell
# Interactive wizard
.\autoclip.bat

# Process a URL directly
.\autoclip.bat process https://youtu.be/VIDEO_ID --model small --max-clips 5 --output .\my_clips

# Check local runtime and create configuration
.\autoclip.bat check
.\autoclip.bat init
.\autoclip.bat config
```

Common process options:

```text
--model, -m TEXT       Whisper model size
--llm TEXT             Ollama model name
--language, -l TEXT    Force language: id | en
--min-duration INT     Minimum clip duration in seconds
--max-duration INT     Maximum clip duration in seconds
--max-clips INT        Maximum clips to generate
--min-score INT        Minimum candidate score (1-10)
--output, -o PATH      Output directory
--no-subtitle          Skip subtitle generation
--no-cache             Ignore cached transcription
--device TEXT          Compute device: cpu | cuda
--verbose              Enable diagnostic output
```

Create configuration file with `autoclip init`, then edit `~/.autoclip/config.yaml` for persistent CLI settings.

```yaml
whisper:
  model: base
  language: null
  device: cpu

ollama:
  model: llama3
  host: http://localhost:11434

clip:
  min_duration: 30
  max_duration: 90
  max_clips: 10
  min_score: 6

subtitle:
  enabled: true
  font: Arial
  font_size: 18
  highlight_color: "&H0000FFFF"
  uppercase: false
```

## Output and storage

CLI exports default to an output directory such as:

```text
autoclip_output/
└── Video_Title/
    ├── source/
    │   └── Video_Title.mp4
    ├── subtitles/
    │   └── clip_01.ass
    ├── clip_01_score9_Opening_Hook.mp4
    └── .cache/
        └── transcript_<hash>.json
```

Studio projects instead keep source media, transcripts, candidates, tracking previews, approved exports, and job history under `~/.autoclip/projects/`.

## Privacy and local processing

AutoClip has no accounts, cloud project storage, or social publishing integration. Video files, transcripts, face-track data, preferences, and exports remain local. Ollama is optional and runs as a local service when selected.

## Development

Use existing virtual environment for Python checks:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Build and test packaged Studio assets only when developing or packaging a source checkout:

```powershell
cd web
npm.cmd ci
npm.cmd run test
npm.cmd run check
npm.cmd run build
npm.cmd run test:browser
```

Production assets are generated in `autoclip/web/static/`. End users launch `autoclip web`; they do not run Vite.

## Documentation

- [Studio workflow and runtime details](./WEB_STUDIO.md)
- [Setup Center and hardware matrix](./SETUP_CENTER.md)
- [Contribution guide](./CONTRIBUTING.md)

## Contributing

Contributions are welcome. Read [CONTRIBUTING.md](./CONTRIBUTING.md), create a focused branch, and include relevant tests with every behavior change.

## License

MIT License. See [LICENSE](./LICENSE).
