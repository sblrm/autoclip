# Contributing to AutoClip

## Run the local studio

Contributors and end users use same public entry point:

```powershell
.\autoclip.bat web
```

Browser opens Home at `http://127.0.0.1:8765`. It checks local runtime and exposes fixed repair plans for missing dependencies. Do not add browser endpoints that accept arbitrary shell commands.

## Validate a change

```powershell
.\.venv\Scripts\python.exe -m pytest -q

cd web
npm.cmd run test
npm.cmd run check
npm.cmd run build
```

The one production build writes package assets to `autoclip/web/static`. Do not add runtime Vite builds to `autoclip web` or compatibility batch wrappers.

GPU smoke tests are opt-in so CPU CI never reports fake readiness:

```powershell
autoclip web
python -c "import torch; print(torch.__version__); print(torch.version.cuda); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0))"
ffmpeg -hide_banner -encoders | Select-String nvenc
$env:AUTOCLIP_RUN_GPU_SMOKE=1; .\.venv\Scripts\python.exe -m pytest tests/test_gpu_smoke.py -q
```

Do not add implicit CLI model/package downloads. Setup Center owns fixed install plans: `onnxruntime-gpu[cuda,cudnn]==1.26.0`, pinned MIT YuNet, and acknowledgement-gated research-only InsightFace assets. Windows GPU tracking uses YuNet CUDA; MediaPipe GPU is Ubuntu-only. Readiness requires live inference or encode smoke, not dependency presence or FFmpeg enumeration alone. No face recognition or embeddings belong in this detector workflow.

## UX expectations

- Local first: no account, cloud storage, or silent install action.
- Indonesian is the default UI language; English must remain usable.
- Runtime status is per engine. Never label the whole studio as GPU when only
  Whisper has CUDA.
- Face tracking must never silently switch to center crop when detection fails.
- Keep the approval gate before final export.

## Pull requests

Keep each change small and include test evidence. For UI work, include a
browser walkthrough of setup, import, tracking-subject selection, preview
approval, and export where practical.
