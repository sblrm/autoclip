<div align="center">

```
   ___         __       ________      
  / _ | __ __/ /____  / ___/ (_)____ 
 / __ |/ // / __/ _ \/ /__/ / / __/ 
/_/ |_|\_,_/\__/\___/\___/_/_/\__/  
```

**AI-Powered Video Clipper for Content Creators**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![Fully Offline](https://img.shields.io/badge/AI-Fully%20Offline-green.svg)](https://ollama.ai)

*Transform long-form videos into viral short clips — automatically, locally, privately.*

</div>

---

AutoClip adalah open-source CLI tool bertenaga AI yang membantu content creator memotong video panjang menjadi clip pendek yang siap diupload ke **TikTok**, **Instagram Reels**, dan **YouTube Shorts** — secara otomatis, offline, dan tanpa biaya API.

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🎬 **Auto Extraction** | Paste link YouTube/TikTok/Instagram → AI detect momen viral secara otomatis |
| 🧠 **LLM Analysis** | Ollama + Llama 3/Mistral/Gemma menganalisis transkrip untuk menemukan momen berpotensi viral |
| 📊 **Viral Scoring** | Setiap clip diberi skor 1-10 berdasarkan potensi viral (emosional, insight, humor, dll.) |
| 📝 **Smart Subtitles** | ASS/SSA subtitle dengan karaoke word-highlight — mirip gaya CapCut viral |
| 📱 **9:16 Output** | Smart crop otomatis ke format vertikal 1080×1920 untuk TikTok/Reels/Shorts |
| 🔒 **100% Offline** | Semua AI processing lokal — tidak ada data yang dikirim ke cloud |
| 🌐 **Bilingual** | Mendukung Bahasa Indonesia dan English secara otomatis |

## Quick Start

### Step 1 — Install Prerequisites

Sebelum menjalankan setup, pastikan berikut sudah terinstall:

| Tool | Kegunaan | Download |
|------|----------|----------|
| **Python 3.10+** | Runtime utama | [python.org](https://www.python.org/downloads/) |
| **FFmpeg** | Video processing | [ffmpeg.org](https://ffmpeg.org/download.html) / `winget install FFmpeg` |
| **Ollama** *(opsional)* | LLM analisis lokal | [ollama.ai](https://ollama.ai) |

Jika menggunakan Ollama, pull model terlebih dahulu:
```bash
ollama pull llama3   # atau: gemma3, mistral, phi4
```

### Step 2 — Clone & Setup

```bash
# Clone repository
git clone https://github.com/your-org/autoclip.git
cd autoclip
```
```powershell
# Windows (PowerShell) — pakai .\ prefix
.\setup.bat

# macOS / Linux
bash setup.sh
```

> **Catatan PowerShell:** PowerShell tidak otomatis menjalankan script dari direktori saat ini. Selalu gunakan `.\` di depan nama script (contoh: `.\setup.bat`, `.\autoclip.bat`).

Setup script akan otomatis:
- Membuat virtual environment (`.venv/`)
- Menginstall semua dependencies (PyTorch CPU, Whisper, dll.)
- Membuat launcher `autoclip.bat` / `autoclip.sh` di root folder

### Step 3 — Jalankan

```powershell
# Windows (PowerShell)
.\autoclip.bat

# macOS / Linux
./autoclip
```

Wizard interaktif akan memandu kamu langkah demi langkah:

```
 Step 1/8  Video URL
  Paste link video kamu (YouTube, TikTok, Instagram, dll.):
  > https://youtu.be/...
  [OK] Platform terdeteksi: YouTube

 Step 2/8  Mode Analisis
  1  AI (Ollama)  — lebih akurat, butuh Ollama running
  2  Heuristic    — offline pure, tanpa AI
  Pilihan [1]:

 Step 3/8  Model Transkripsi (Whisper)
  ...

 Step 8/8  Folder Output
  Folder output (Enter untuk default: ./autoclip_output/...):
  >
```

### Mode CLI Langsung (Advanced)

Bisa juga dijalankan langsung tanpa wizard:

```bash
autoclip process https://youtu.be/VIDEO_ID
autoclip process https://youtu.be/VIDEO_ID --model small --max-clips 5 --output ./my_clips
autoclip check     # Cek semua dependencies
autoclip init      # Buat config file
autoclip config    # Tampilkan konfigurasi saat ini
```

### GPU face tracking and NVENC

Run `autoclip web`. Browser opens AutoClip Home automatically; Node, Vite, and manual CUDA checks are not needed to launch it. Home names only required blockers. Use **Perbaiki setup wajib** for the fixed local repair plan, then continue with **Mulai proyek**.

Auto is valid on CPU: it selects a verified CPU tracker with `libx264` when GPU evidence is missing. Explicit GPU requires both live face-tracker inference and real `h264_nvenc` smoke output; it reports recovery steps instead of silently using CPU or a center crop. **Performa** now shows a direct **Setup GPU tracking** checklist with fixed install buttons for PyTorch CUDA 12.8, ONNX Runtime CUDA, and YuNet. Advanced Settings exposes explicit MediaPipe, YuNet, SCRFD, RetinaFace, and encoder choices.

For a Windows RTX 5070, working PyTorch CUDA is enough; do not install CUDA Toolkit solely for AutoClip. Use the fixed buttons in **Setup GPU tracking**, restart if PyTorch asks for it, then select **Cek ulang GPU**. Live CUDA inference must pass before Auto selects `yunet_cuda`. FFmpeg NVENC also needs a successful real `h264_nvenc` encode smoke, not only an encoder-list match. Auto falls back to `libx264`; explicitly selected NVENC fails with `nvenc_error` when unusable.

YuNet model assets are MIT. Optional InsightFace SCRFD and RetinaFace model assets are research-only/non-commercial and require acknowledgement before download. Detection stays local; AutoClip does not use face recognition or embeddings.

```powershell
autoclip web
```


## 📁 Output Structure

```
autoclip_output/
└── Video_Title/
    ├── source/
    │   └── Video_Title.mp4           # Original downloaded video
    ├── subtitles/
    │   ├── clip_01.ass               # Subtitle untuk clip 1
    │   └── clip_02.ass               # Subtitle untuk clip 2
    ├── clip_01_score9_Hook_Pembuka.mp4     # Clip dengan subtitle burned-in
    ├── clip_02_score8_Insight_Mendalam.mp4
    └── .cache/
        └── transcript_<hash>.json    # Cached transcription
```

## ⚙️ Configuration

Edit `~/.autoclip/config.yaml` (buat dengan `autoclip init`):

```yaml
whisper:
  model: base          # tiny | base | small | medium | large-v3
  language: null       # null = auto-detect, "id" = Indonesia, "en" = English
  device: cpu          # cpu | cuda (untuk GPU)

ollama:
  model: llama3        # llama3 | mistral | gemma | phi3
  host: http://localhost:11434

clip:
  min_duration: 30     # Minimal durasi clip (detik)
  max_duration: 90     # Maksimal durasi clip (detik)
  max_clips: 10        # Maksimal jumlah clip
  min_score: 6         # Skor minimal untuk include clip (1-10)

subtitle:
  enabled: true
  font: Arial
  font_size: 18
  highlight_color: "&H0000FFFF"   # Kuning untuk kata aktif
  uppercase: false                # Set true untuk gaya TikTok caps
```

## 🎯 CLI Reference

```
autoclip --help

Commands:
  process   🚀 Process video URL through full pipeline
  init      📁 Initialize config file
  check     🔍 Check all dependencies
  config    ⚙️  Show current configuration

autoclip process --help
  URL                   Video URL (required)
  --model, -m TEXT      Whisper model size
  --llm TEXT            Ollama model name
  --language, -l TEXT   Force language: id | en
  --min-duration INT    Minimum clip duration in seconds
  --max-duration INT    Maximum clip duration in seconds
  --max-clips INT       Maximum clips to generate
  --min-score INT       Minimum viral score (1-10)
  --output, -o PATH     Output directory
  --no-subtitle         Skip subtitle generation
  --no-cache            Ignore cached transcription
  --device TEXT         Computing device: cpu | cuda
  --verbose             Enable debug logging
```

## 🧪 Development

```bash
# Install with dev dependencies
poetry install

# Run tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=autoclip --cov-report=term-missing

# Lint
poetry run ruff check autoclip/

# Type check
poetry run mypy autoclip/
```

Build browser assets only when developing or packaging a source checkout. End users run `autoclip web`; they do not run Vite.

```powershell
cd web
npm.cmd ci
npm.cmd run build
```

## 🗺️ Roadmap

### v0.1.0 — Current (MVP)
- [x] Video download (YouTube, TikTok, Instagram, 1000+ platforms via yt-dlp)
- [x] Speech-to-text transcription (Whisper)
- [x] Viral moment detection (Ollama LLM with heuristic fallback)
- [x] Smart crop to 9:16 vertical format (FFmpeg)
- [x] ASS/SSA subtitle with karaoke word-highlight
- [x] Bilingual support (Indonesia + English)

### v0.2.0 — Hook Editor AI
- [ ] AI-generated hooks (teks pembuka yang menarik)
- [ ] Hook overlay generator
- [ ] A/B testing prompts

### v0.3.0 — Smart Layout
- [ ] Face detection & auto-crop (MediaPipe)
- [ ] Split-screen layout for debates
- [ ] Picture-in-Picture for gaming reactions
- [ ] Auto-focus on active speaker

### v0.4.0 — Batch & Upload
- [ ] Batch processing (multiple URLs)
- [ ] Preset template system
- [ ] Direct upload to TikTok/YouTube/Instagram

## 🤝 Contributing

Kontribusi sangat diterima! Lihat [CONTRIBUTING.md](./CONTRIBUTING.md) untuk panduan.

1. Fork repository
2. Buat feature branch: `git checkout -b feat/amazing-feature`
3. Commit changes: `git commit -m 'feat: add amazing feature'`
4. Push ke branch: `git push origin feat/amazing-feature`
5. Buat Pull Request

## 📄 License

MIT License — lihat [LICENSE](./LICENSE) untuk detail lengkap.

---

<div align="center">
  Made with ❤️ for the content creator community
</div>
