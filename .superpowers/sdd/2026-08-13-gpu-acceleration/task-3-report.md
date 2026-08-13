# Task 3 report: BLOCKED

## Scope and files

Created:

- `autoclip/web/detectors.py`
- `autoclip/web/acceleration_manager.py`
- `tests/test_detectors.py`
- `tests/test_acceleration_manager.py`
- `.superpowers/sdd/2026-08-13-gpu-acceleration/task-3-report.md`

Required but not modified:

- `autoclip/web/tracking.py`

No FastAPI, UI, rendering, Task 2 catalog/manager, recognition model, embedding, or persistence integration was changed. No commit was attempted because no Git root exists.

## TDD evidence

### RED

Command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_detectors.py tests/test_acceleration_manager.py -q
```

Result: exit 1, `13 failed`. Expected causes:

- `ModuleNotFoundError: No module named 'autoclip.web.detectors'`
- `ModuleNotFoundError: No module named 'autoclip.web.acceleration_manager'`
- `TypeError: MediaPipeTasksDetector.__init__() got an unexpected keyword argument 'delegate'`

### GREEN progress before blocker

Same focused command after creating Task 3 modules:

```text
12 passed, 1 failed
```

Only remaining failure:

```text
TypeError: MediaPipeTasksDetector.__init__() got an unexpected keyword argument 'delegate'
```

### Required final verification

Command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_detectors.py tests/test_acceleration_manager.py tests/test_web_tracking.py -q
```

Result: exit 1, `15 passed, 1 failed`. Same load-bearing delegate failure above.

Legacy compatibility command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_mediapipe_tasks_detector.py tests/test_face_detector_fixture.py -q
```

Result: exit 0, `2 passed`.

Compile smoke command:

```powershell
.\.venv\Scripts\python.exe -m compileall -q autoclip/web/detectors.py autoclip/web/acceleration_manager.py tests/test_detectors.py tests/test_acceleration_manager.py
```

Result: exit 0.

Ruff could not run because this venv reports:

```text
G:\App\AutoClip\.venv\Scripts\python.exe: No module named ruff
```

## Implemented behavior

- `VideoFaceDetector` protocol and injectable `DetectorFactory.create(resolution)`.
- Strict single ORT provider request and post-construction provider verification. CUDA paths never include `CPUExecutionProvider`.
- YuNet 320x320 letterbox, BGR-to-RGB float32 NCHW tensor, padding/scale reversal, IoU 0.3 NMS, clamped normalized centers, stable confidence/x/y ordering.
- Detector-only SCRFD/RetinaFace adapter path with no recognition model, embeddings, or persisted identity state.
- Live status probes for exact Ubuntu distro ID, NVIDIA name/driver, PyTorch CUDA, ORT providers/preload, model size/hash, detector construction, and generated-frame inference.
- GPU status verifies returned detector engine/provider before ready. Empty face output still counts as successful inference; exception details expose only exception type.
- Missing ONNX model cache reports `missing`; non-Ubuntu MediaPipe GPU reports `unsupported`; failed GPU delegate/session reports `failed` without CPU provider substitution.

## Self-review

- Strict-provider tests prove `yunet_cuda` requests exactly `["CUDAExecutionProvider"]` and rejects a CPU-only created session.
- Live-probe test proves `detect()` runs once before `ready`; it does not infer readiness from package/provider enumeration alone.
- Factory and manager remain injectable, so tests require no real CUDA, MediaPipe, ONNX Runtime, or downloaded models.
- No fallback path changes a requested GPU engine into CPU.
- No recognition or embedding code exists.
- Current default `DetectorFactory.create()` for MediaPipe cannot work until the required `tracking.py` change lands; this is why Task 3 is not complete.

## Exact blocker

Two `apply_patch` attempts to modify existing `autoclip/web/tracking.py` were rejected before any edit with:

```text
apply_patch verification failed: Failed to read file to update G:\App\AutoClip\autoclip\web\tracking.py: fs sandbox helper failed with status exit code: 1: windows sandbox failed: helper_unknown_error: setup refresh had errors
```

Required pending edit:

1. Extend `MediaPipeTasksDetector.__init__` with optional `delegate`, plus `engine`, `provider`, and `model_id` protocol metadata while preserving existing defaults.
2. Pass `delegate` into `mp.tasks.BaseOptions(model_asset_path=..., delegate=delegate)`.
3. Re-run required final verification until all 16 tests pass.

Status remains **BLOCKED**. Do not treat partial green results as completion.
