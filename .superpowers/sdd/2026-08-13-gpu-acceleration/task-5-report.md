# Task 5 report: NVENC checks and tracking render integration

## Status

COMPLETE. Tracking resolves and persists one verified detector run, preview/export reuse its
saved trajectory, and every render records detector/encoder metadata. Explicit NVENC failures
remain structured and never substitute a CPU encoder.

No Git command was run.

## Changed files

- `autoclip/utils/ffmpeg.py`
- `autoclip/core/tracker.py`
- `autoclip/web/rendering.py`
- `tests/test_nvenc.py`
- `tests/test_tracking_render_integration.py`
- `.superpowers/sdd/2026-08-13-gpu-acceleration/task-5-report.md`

Task 4 persistence already supported the required two-stage flow: an initial
`save_clip_tracking_resolution(..., None)`, followed by a validated upsert with the saved
trajectory artifact ID. No store API change was needed.

## RED

Command, run before production changes:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_nvenc.py tests/test_tracking_render_integration.py -q
```

Output:

```text
collected 11 items
tests\test_nvenc.py FFFFFFFFF
tests\test_tracking_render_integration.py FF

11 failed in 0.55s
```

Expected failures included:

```text
ImportError: cannot import name 'list_video_encoders' from 'autoclip.utils.ffmpeg'
ImportError: cannot import name 'EncoderCapability' from 'autoclip.utils.ffmpeg'
Failed: DID NOT RAISE <class 'autoclip.web.acceleration.TrackerUnavailable'>
```

These proved the absent encoder capability/argument contracts and absent saved-resolution
guard before implementation.

## GREEN

Focused command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_nvenc.py tests/test_tracking_render_integration.py -q
```

Output:

```text
collected 11 items
tests\test_nvenc.py .........
tests\test_tracking_render_integration.py ..
11 passed in 0.54s
```

Required regression command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_nvenc.py tests/test_tracking_render_integration.py tests/test_tracking_service.py tests/test_web_tracking.py -q
```

Output:

```text
collected 16 items
tests\test_nvenc.py .........
tests\test_tracking_render_integration.py ..
tests\test_tracking_service.py ..
tests\test_web_tracking.py ...
16 passed in 0.61s
```

Full-suite verification:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Output:

```text
collected 244 items
244 passed, 3 warnings in 7.35s
```

The three warnings are existing FastAPI/Starlette deprecations.

Syntax verification:

```powershell
.\.venv\Scripts\python.exe -m compileall -q autoclip\utils\ffmpeg.py autoclip\core\tracker.py autoclip\web\rendering.py tests\test_nvenc.py tests\test_tracking_render_integration.py
```

Output: exit 0, no diagnostics.

`ruff` and `mypy` could not run because both modules are absent from this venv:

```text
G:\App\AutoClip\.venv\Scripts\python.exe: No module named ruff
G:\App\AutoClip\.venv\Scripts\python.exe: No module named mypy
```

## Implementation

- Added immutable `EncoderCapability` and `VideoEncoding` contracts.
- `list_video_encoders()` parses only `V.....`/`V....D` rows from
  `ffmpeg -hide_banner -encoders`; audio and subtitle names cannot be mistaken for video
  encoders.
- `smoke_test_encoder()` performs the required generated 16x16 one-frame encode and keeps the
  final 1000 output characters on failure.
- `resolve_video_encoding()` uses exact required FFmpeg arguments. `auto` falls back to
  `libx264` only when verified H.264 NVENC is not ready. Explicit H.264/HEVC NVENC raises
  `EncoderUnavailable` containing `nvenc_error` and the probe reason.
- `apply_face_crop()` accepts the resolved `VideoEncoding`, appends its arguments verbatim,
  and retains AAC muxing. Its optional compatibility path keeps existing CLI callers and all
  tracker/clipper tests green.
- `TrackingService.detect_tracks()` loads the persisted project selection, resolves live
  status, creates one exact detector, performs one detection pass, and saves the resolution
  with no trajectory ID. Legacy injected zero-argument detector factories remain supported for
  existing unit/CLI callers.
- Preview writes tracker engine/provider/model into the trajectory JSON, saves the trajectory
  artifact, then updates the same clip resolution with that artifact ID.
- Preview and approved export load the saved resolution, resolve a smoke-tested encoder, and
  call the cropper using the same saved centers. Export never detects again or changes the
  selected track/detector. The approval check remains before export rendering.
- Preview/export artifact metadata contains `encoder_mode`, `encoder`, `tracker_engine`,
  `provider`, `model_id`, and `trajectory_artifact_id`.
- A missing saved resolution raises structured `TrackerUnavailable("tracker_error: ...")`
  before trajectory construction or cropper invocation; no center crop is used.

## Self-review

- Parser coverage includes misleading audio and subtitle encoder rows.
- Smoke tests use injected runners; render tests use injected detector/cropper/capability fakes.
  No real GPU or FFmpeg encoder is required.
- Exact libx264, H.264 NVENC, and HEVC NVENC argument lists are asserted literally.
- Explicit NVENC failure is asserted as structured and has no CPU substitution branch.
- Integration asserts one detector creation, initial null trajectory ID, later artifact-ID
  update, identical preview/export centers, different output dimensions, and exact metadata.
- Missing-resolution integration asserts zero cropper calls.
- Full suite covers legacy tracker, clipper, FastAPI, persistence, acceleration, and approval
  paths after the integration change.

## Concerns

- Default render capability discovery executes local FFmpeg enumeration and NVENC smoke tests
  at render time. Tests deliberately inject capabilities because CI/workstations may lack
  FFmpeg or NVIDIA hardware.
- Static lint/type tools are declared as development dependencies but are not installed in the
  current venv; pytest and compile verification are green.

## Review fix round 1/5

Status: COMPLETE.

### Findings verified

- `render_preview()` checked for face tracks before requiring a saved
  `ClipTrackingResolution`. A fresh clip therefore entered `detect_tracks()` and constructed a
  detector from the preview path. This violated the detect-once boundary and prevented the
  required structured missing-resolution error.
- Task 5 inserted `encoding` between legacy `smart_crop_clip()` optional positional arguments.
  An old call supplying `ema_alpha`, `sample_every_n_frames`, `use_mediapipe`, and
  `deadzone_fraction` positionally instead bound them to the wrong parameters.

### P1 TDD evidence

Added a fresh no-track/no-resolution clip test with a detector factory sentinel, complete clip
state snapshot, and artifact/track/resolution assertions.

RED command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_tracking_render_integration.py::test_preview_without_detection_run_fails_before_constructing_detector -q
```

RED output:

```text
FAILED tests/test_tracking_render_integration.py::test_preview_without_detection_run_fails_before_constructing_detector
autoclip\web\rendering.py:164: in render_preview
    self.detect_tracks(clip_id, report)
tests\test_tracking_render_integration.py:181: in create
    raise AssertionError("preview must not construct a detector")
1 failed in 0.48s
```

Fix: `render_preview()` now calls `_require_resolution()` immediately after loading the clip,
before checking selected-track state or doing trajectory/crop work. The implicit
`detect_tracks()` call was removed; detection remains explicit only through `detect_tracks()`.

GREEN command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_tracking_render_integration.py::test_preview_without_detection_run_fails_before_constructing_detector -vv -s
```

GREEN output:

```text
tests/test_tracking_render_integration.py::test_preview_without_detection_run_fails_before_constructing_detector PASSED
1 passed in 0.32s
```

The test confirms `TrackerUnavailable.error_code == "tracker_error"`, zero detector factory
calls, unchanged clip state, no tracks, no resolution, and no artifacts.

### P2 TDD evidence

Added a legacy invocation passing every pre-Task-5 optional argument positionally and captured
the exact trajectory-builder/cropper arguments.

RED command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_tracker.py::test_smart_crop_clip_preserves_legacy_positional_optional_arguments -q
```

RED output:

```text
FAILED tests/test_tracker.py::test_smart_crop_clip_preserves_legacy_positional_optional_arguments
{'ema_alpha': 7} != {'ema_alpha': 0.2}
{'sample_every_n_frames': False} != {'sample_every_n_frames': 7}
{'use_mediapipe': 0.08} != {'use_mediapipe': False}
{'deadzone_fraction': 0.04} != {'deadzone_fraction': 0.08}
1 failed in 0.42s
```

Fix: moved new `encoding` parameter after all legacy optional parameters. Existing positional
ordering is exact; new integrations continue passing `encoding` by keyword.

GREEN command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_tracker.py::test_smart_crop_clip_preserves_legacy_positional_optional_arguments -q
```

GREEN output:

```text
tests\test_tracker.py .
1 passed in 0.34s
```

### Final verification

Focused Task 5 and tracker/web regression command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_nvenc.py tests/test_tracking_render_integration.py tests/test_tracking_service.py tests/test_web_tracking.py tests/test_tracker.py -q
```

Output:

```text
collected 36 items
tests\test_nvenc.py .........
tests\test_tracking_render_integration.py ...
tests\test_tracking_service.py ..
tests\test_web_tracking.py ...
tests\test_tracker.py ...................
36 passed in 1.33s
```

Full suite:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Output:

```text
collected 246 items
246 passed, 3 warnings in 7.36s
```

Warnings remain the same pre-existing FastAPI/Starlette deprecations.

Syntax verification:

```powershell
.\.venv\Scripts\python.exe -m compileall -q autoclip\web\rendering.py autoclip\core\tracker.py tests\test_tracking_render_integration.py tests\test_tracker.py
```

Output: exit 0, no diagnostics.

### Self-review

- Preview has no code path to detector construction or detection. Missing resolution fails
  before selected-track mutation, progress reporting, encoder probing, trajectory creation, or
  crop invocation.
- `detect_tracks()` remains the only detection entry point in `TrackingService`.
- Old `smart_crop_clip` positional ordering through `deadzone_fraction` is restored verbatim.
  `encoding` is additive at the end and is passed by keyword internally.
- Both fixes are isolated; encoder strictness, trajectory identity reuse, approval gate, and
  artifact metadata remain unchanged.
