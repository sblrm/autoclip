# Task 8 brief — CLI policy, docs, full verification

Implement Task 8 only from `docs/superpowers/plans/2026-08-13-gpu-acceleration.md`.

## Scope

Modify only as required:

- `autoclip/core/clipper.py`
- `autoclip/core/tracker.py`
- `autoclip/cli/__init__.py`
- `README.md`
- `SETUP_CENTER.md`
- `CONTRIBUTING.md`
- `tests/test_tracker.py`
- `tests/test_clipper.py`
- `tests/test_cli_web.py`
- create `tests/test_gpu_smoke.py`

Do not change Task 1–6 contracts except wiring their public APIs into old CLI code. No browser/UI work. No implicit model/package download from CLI. Use `apply_patch` only. No Git.

## Existing contracts

- `TrackerConfig.engine` and `OutputConfig.encoder_mode` are already compatible. Exact engines: `auto`, `mediapipe_cpu`, `mediapipe_gpu`, `yunet_cpu`, `yunet_cuda`, `scrfd_cpu`, `scrfd_cuda`, `retinaface_cpu`, `retinaface_cuda`.
- `AccelerationSelection`, `TrackerUnavailable`, `EncoderUnavailable` live in `autoclip.web.acceleration`.
- `AccelerationManager().status().resolve(AccelerationSelection(...))` returns verified selection. Explicit unavailable tracker must raise `TrackerUnavailable` whose message starts `tracker_error: engine=... state=...`. Explicit unavailable NVENC must raise `EncoderUnavailable` with `nvenc_error`.
- `resolve_video_encoding(requested, capabilities)` in `autoclip.utils.ffmpeg` provides strict `VideoEncoding`. Its NVENC checks require real smoke capability; explicit request never silently falls back.
- Current `clipper.create_clips` catches *every* `RuntimeError` per clip and `_export_clip_tracked` catches `ImportError` then static-crops. This is legacy behavior to narrow: requested GPU/face engine failure must escape as structured `TrackerUnavailable` / `EncoderUnavailable`, not return a successful static crop. `tracker.enabled=False` still intentionally centre-crops.
- `smart_crop_clip(..., encoding=...)` and `apply_face_crop(..., encoding=...)` already support a saved encoding. Preserve existing positional optional parameters exactly. `output_config.video_codec` is legacy and must not override resolved `encoder_mode`.
- CLI compatibility wrapper is `autoclip/cli/__init__.py`; old process flow lives `autoclip/cli.py` and calls `_create_clips` imported from clipper. Keep `autoclip web` working.

## Required behavior

1. At top of clipping, when tracking enabled, resolve using `AccelerationManager` and `AccelerationSelection(tracker_config.engine, output_config.encoder_mode)` before FFmpeg/static export. Thread resulting `VideoEncoding` into tracked and non-tracked FFmpeg flows.
2. Explicit tracking engine missing/unsupported/failed: raise `TrackerUnavailable` with repair guidance containing `autoclip web`. Do not attempt static crop. Do not swallow it in generic per-clip `except RuntimeError`.
3. For tracker engine `auto`, resolved CPU MediaPipe/YuNet is valid. If no resolver candidate exists, raise structured `TrackerUnavailable`; do not static crop because user set tracking enabled.
4. If `tracker.enabled is False`, retain current intentional static centre crop. Encoder selection still uses strict video resolver; explicit unusable NVENC should raise `EncoderUnavailable`, Auto can use libx264.
5. CLI never downloads models/packages. Existing `web` command stays guided launch behavior.

## Tests

Start RED. Add deterministic test proving a config with `tracker.enabled=True`, `engine="yunet_cuda"` and unavailable fake/resolver status raises `TrackerUnavailable` from `create_clips` before export. Test message contains engine and `autoclip web`; prove `run_ffmpeg` / static export was not used.

Test explicit unavailable `h264_nvenc` does not silently use `libx264`; test tracker-disabled configuration retains centre crop. Use monkeypatchable resolver/manager boundary instead of depending on actual hardware.

`tests/test_gpu_smoke.py` must be opt-in and never make normal CPU CI falsely claim a GPU ready. Define `@pytest.mark.gpu` tests which call current real `AccelerationManager` and either:

- run and assert actual ready provider/smoke when `AUTOCLIP_RUN_GPU_SMOKE=1`; or
- skip with clear evidence message when that explicit environment flag is absent.

This keeps `python -m pytest -q` green on CPU systems while preserving a real hardware smoke command. Register marker if project config requires it. Do not fake GPU readiness.

## Documentation facts — exact

- Windows RTX 5070 path: current PyTorch CUDA can work; do **not** install CUDA Toolkit solely for AutoClip.
- Setup Center installs `onnxruntime-gpu[cuda,cudnn]==1.26.0`, then pinned YuNet model; Recheck must pass live `CUDAExecutionProvider` inference; Auto then selects `yunet_cuda`.
- NVENC requires successful `h264_nvenc` FFmpeg smoke, not mere encoder listing.
- Windows GPU face tracking is YuNet CUDA. MediaPipe GPU is Ubuntu-only and needs live VIDEO inference.
- YuNet is MIT. InsightFace model assets are research-only/non-commercial, acknowledgement required. Face work stays local and no embeddings/recognition are used.
- Exact verification commands:

```powershell
autoclip web
python -c "import torch; print(torch.__version__); print(torch.version.cuda); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0))"
ffmpeg -hide_banner -encoders | Select-String nvenc
$env:AUTOCLIP_RUN_GPU_SMOKE=1; .\.venv\Scripts\python.exe -m pytest tests/test_gpu_smoke.py -q
```

Document manual matrix with Windows RTX 5070 (`yunet_cuda` ready, selected-track preview, `h264_nvenc` export metadata), Ubuntu NVIDIA (`mediapipe_gpu` verified live VIDEO inference), and CPU-only (Auto CPU tracker/libx264/no false GPU badge). Mention preview/export must use matching saved trajectory centers and selected face track, including forced face-loss gap hold/ease review.

## Verify

Run first focused command from repository root using `.venv` if available:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_tracker.py tests/test_clipper.py tests/test_cli_web.py tests/test_gpu_smoke.py -q
```

Then full Python suite. Task 7 frontend may be in progress; do not edit UI, but report frontend result only after coordinating with root or state it was not safe to run concurrently. Add `task-8-report.md` with RED/GREEN/full evidence, changed files, and genuine unavailable tools/errors. Do not claim all project verification green until root runs Task 7 + final suite.
