# Task 8 report — CLI policy, docs, verification

## Result

CLI clipping now resolves tracker and encoder capabilities before export. Enabled tracking never silently center-crops. Explicit unavailable tracker errors include engine/state and `autoclip web` repair guidance. Explicit NVENC uses real FFmpeg smoke capability and never falls back to `libx264`. Tracker-disabled export intentionally keeps center crop while still applying strict encoder selection.

Resolved face engines use one `DetectorFactory` VIDEO detector per clip with monotonic timestamps. Resolved `VideoEncoding` reaches both tracked and static FFmpeg paths. No model or package installer is called from CLI code.

## TDD evidence

RED:

```text
tests/test_clipper.py + tests/test_tracker.py
43 collected; 38 passed, 5 failed

Failures proved:
- unavailable yunet_cuda did not raise
- unavailable h264_nvenc did not raise
- legacy video_codec overrode encoder_mode=auto
- tracked export did not receive encoding
- build_crop_trajectory did not accept resolved acceleration
```

Additional RED for runtime detector failure:

```text
21 collected; 20 passed, 1 failed
RuntimeError: CUDA execution failed
```

GREEN focused:

```text
.\.venv\Scripts\python.exe -m pytest tests/test_acceleration_manager.py tests/test_nvenc.py tests/test_tracker.py tests/test_clipper.py tests/test_cli_web.py tests/test_gpu_smoke.py -q
64 passed, 3 skipped in 1.51s
```

GPU skips are intentional unless `AUTOCLIP_RUN_GPU_SMOKE=1`.

## Full evidence

```text
.\.venv\Scripts\python.exe -m pytest -q
265 passed, 3 skipped, 3 warnings in 8.68s
```

Warnings are existing Starlette/FastAPI deprecations. Python compile check passed:

```text
.\.venv\Scripts\python.exe -m compileall -q autoclip
exit 0
```

Real Windows hardware smoke:

```text
$env:AUTOCLIP_RUN_GPU_SMOKE=1; .\.venv\Scripts\python.exe -m pytest tests/test_gpu_smoke.py -q
1 passed, 1 skipped, 1 failed
```

- `h264_nvenc`: passed real smoke encode.
- `yunet_cuda`: honest failure, `Verified detector model is not cached`.
- Ubuntu MediaPipe GPU: skipped because host is Windows.

This result proves FFmpeg NVENC works on current host but YuNet must still be installed through Setup Center and Rechecked before Windows GPU face tracking can be marked ready. CLI did not download it.

## Reviewer P1 corrections

Two added tests first failed as expected:

```text
2 collected, 2 failed
- DetectorFactory initialization RuntimeError was swallowed by create_clips
- listed NVENC with failed live encode was incorrectly reported ready
```

Fixes:

- Detector factory/create/enter errors now become `tracker_error: engine=... state=failed` with `autoclip web` guidance; detector/capture cleanup runs once and no static export occurs.
- `AccelerationManager` now uses shared encoder enumeration plus `smoke_test_encoder` for the real runtime probe. Injected legacy test probes remain supported.
- Tiny 16x16 and 128x128 NVENC probes were rejected by this RTX/FFmpeg build as below its supported size. Probe now generates one representative 640x360 frame. Direct 640x360 `h264_nvenc` command and opt-in test both passed.

Focused Ruff could not run because current project virtual environment does not contain Ruff:

```text
G:\App\AutoClip\.venv\Scripts\python.exe: No module named ruff
```

## Changed files

- `autoclip/core/clipper.py`
- `autoclip/core/tracker.py`
- `autoclip/utils/ffmpeg.py`
- `autoclip/web/acceleration_manager.py`
- `tests/test_clipper.py`
- `tests/test_tracker.py`
- `tests/test_nvenc.py`
- `tests/test_acceleration_manager.py`
- `tests/test_gpu_smoke.py`
- `pyproject.toml`
- `README.md`
- `SETUP_CENTER.md`
- `CONTRIBUTING.md`

`autoclip/cli/__init__.py` and `tests/test_cli_web.py` needed no source change; existing `autoclip web` compatibility test remains green.

## Coordination limits

Task 7 frontend was being edited concurrently, so Task 8 did not run or modify frontend checks/builds. Root must run final frontend verification after Task 7 settles. Workspace has no usable Git repository, so no commit was created.
