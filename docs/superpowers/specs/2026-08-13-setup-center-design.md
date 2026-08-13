# AutoClip Setup Center Design

## Goal

Make AutoClip understandable and repairable on first launch. A new user can see what works, install missing local tools, choose CPU or NVIDIA GPU processing, and understand which engine uses that choice before importing a video.

## Product flow

1. The root page opens a setup-aware welcome screen until essential requirements are ready.
2. The welcome screen explains the five-step editing flow: set up, import, analyze, choose subject, approve and export.
3. Setup Center lists every local dependency with one honest state: `ready`, `missing`, `installing`, `failed`, or `unsupported`.
4. Essential dependencies are FFmpeg, OpenCV, MediaPipe Tasks, and Whisper. Ollama remains optional. No network process starts without a user pressing Install.
5. Hardware is per engine. Whisper reports CPU or NVIDIA GPU from PyTorch. Face tracking and rendering remain CPU unless their own runtime is proved accelerated. A global GPU label is forbidden.
6. The GPU action is opt-in. It shows the detected adapter, driver, exact PyTorch command, and restart requirement. It reinstalls the installed PyTorch version from the CUDA wheel index, then rechecks `torch.cuda.is_available()`.
7. A failed install persists concise output and the exact command. User can retry or copy diagnostics.

## Architecture

`SetupManager` owns read-only probes and explicit install plans. It only runs allow-listed commands: Windows Package Manager for FFmpeg, the active Python environment's pip for Python tools, and the official PyTorch CUDA wheel index for a requested GPU upgrade. It returns structured status and never invokes a shell.

`usable_studio` wraps the existing FastAPI server with Setup Center endpoints and serves an isolated Vite entrypoint. This avoids changing project editing behaviour while enabling a guided first-run experience.

## Public API

- `GET /api/setup/status` returns components, hardware, first-run progress, and recent install log.
- `POST /api/setup/install` accepts `{ "component": "ffmpeg" | "opencv" | "face_tracking" | "whisper_gpu" }` and returns a serial job id.
- `POST /api/setup/recheck` returns refreshed status.

## Safety rules

- Localhost only; no account or telemetry.
- Every install plan is allow-listed and visible in the UI before execution.
- No `shell=True`, user-supplied command, arbitrary package, elevated prompt, or hidden fallback.
- Installer writes under the active Python environment or Windows Package Manager's user-scoped location.
- GPU upgrade checks NVIDIA hardware first and never claims face tracking/rendering became GPU accelerated.

## Verification

- Unit tests cover absent/present tools, NVIDIA detection, CPU-only PyTorch, exact GPU install command, and rejected unknown component.
- API tests cover status, queued install lifecycle, and a structured unsupported-GPU error.
- React tests cover first-run tutorial, install CTA, component-specific hardware copy, and no misleading global GPU label.
- Browser smoke test verifies welcome screen, Setup Center, and editor entry when all required tools are ready.
