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

---

## Blocker resolved and final verification (editor recovery)

`autoclip/web/tracking.py` now accepts optional keyword-only `delegate`,
`engine`, `provider`, and `model_id` fields. Its positional defaults remain
`model_path=None` and `min_confidence=0.5`, preserving legacy construction.
`MediaPipeTasksDetector.__enter__` passes the selected delegate to:

```python
mp.tasks.BaseOptions(model_asset_path=str(self.model_path), delegate=self.delegate)
```

The delegate test fixture assertion was corrected to read its stored kwargs;
the fake intentionally stores a dict and did not expose `.running_mode`.

Final required command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_detectors.py tests/test_acceleration_manager.py tests/test_web_tracking.py -q
```

Result: exit 0, `16 passed in 0.15s`.

Final self-review:

- Existing callers retain the old two positional parameters and CPU metadata defaults.
- GPU delegate is explicit and is passed to MediaPipe `BaseOptions`; `RunningMode.VIDEO` and `detect_for_video` remain unchanged.
- Detector metadata now satisfies the shared `VideoFaceDetector` contract without changing tracking/render integration.
- Exact Task 3 suite is green. No new scope or Git action was introduced.

Status: **DONE**.

---

## Review fix round 1/5

### Findings addressed

- Added public `ModelManager.is_installed(plan_id) -> bool`. It delegates to
  Task 2's existing direct-file checksum validator and archive manifest plus
  extracted-payload validator. `AccelerationManager` now delegates cache
  readiness to this method instead of comparing every destination to the
  download archive size/SHA.
- `ModelManager` accepts an optional internal model-plan mapping so
  `AccelerationManager` uses one validator for production catalog plans and
  injected test plans.
- `InsightFaceOnnxDetector` now uses RGB float32 `(pixel - 127.5) / 128.0`.
  YuNet retains RGB `/ 255.0`.
- `InsightFaceDecoder` accepts only valid three-stride anchor layouts (six
  score/bbox tensors, optionally three landmark tensors). It no longer
  interprets malformed InsightFace outputs as a YuNet empty-face result.

### TDD evidence

RED command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_model_manager.py tests/test_detectors.py tests/test_acceleration_manager.py -q
```

Result: exit 1, `5 failed, 24 passed`.

- direct/archive `is_installed` tests failed because public method was absent;
- archive SCRFD cache status was `missing` instead of `ready`;
- SCRFD input used YuNet `/255` values;
- malformed singleton output returned no faces instead of raising.

The first GREEN run exposed a test-fixture error: stride 16/32 tensors were
zero-length, which cannot represent valid detector outputs. Fixture was
corrected to valid zero-score tensors with each stride's full anchor count.

Focused GREEN command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_model_manager.py tests/test_detectors.py tests/test_acceleration_manager.py -q
```

Result: exit 0, `29 passed in 0.29s`.

Final verification command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_detectors.py tests/test_acceleration_manager.py tests/test_web_tracking.py tests/test_model_manager.py -q
```

Result: exit 0, `32 passed in 0.29s`.

### Added coverage and self-review

- Direct YuNet cache: `is_installed` changes from true to false after a
  same-location payload tamper.
- Archive model: `is_installed` changes from true to false after extracted
  ONNX tamper; cached archive SCRFD produces `ready` status through
  `AccelerationManager`.
- Known SCRFD fixture proves BGR-to-RGB centered normalization and anchored
  stride-8 face center `(0.5, 0.5)` at confidence `0.95`.
- Malformed one-output ONNX result raises instead of reporting an empty face
  list, so live status cannot falsely infer a valid detector path.
- CUDA provider selection, MediaPipe legacy defaults, extraction-only scope,
  and no-embedding boundary remain unchanged.

Review fix round 1/5 status: **DONE**.
