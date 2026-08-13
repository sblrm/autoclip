# Task 1 report: stable acceleration contracts and config migration

## Implementation

- Added `autoclip/web/acceleration.py` with the required literal contracts:
  `TrackerEngine`, `EncoderMode`, and `RuntimeState`.
- Added frozen `AccelerationSelection`, `ResolvedAcceleration`, `AccelerationStatus`,
  `EngineProbe`, and `EncoderProbe` objects. Probe mappings are normalized and
  exposed as immutable mappings.
- Implemented deterministic resolution:
  - Explicit trackers require a `ready` probe and otherwise raise
    `TrackerUnavailable` with the engine, runtime state, and probe reason.
  - Automatic tracker order is Ubuntu MediaPipe GPU, YuNet CUDA, MediaPipe CPU,
    then YuNet CPU; non-Ubuntu starts with YuNet CUDA. It raises
    `no_tracker_engine` when none are ready.
  - Explicit NVENC modes require a ready encoder and otherwise raise
    `EncoderUnavailable` containing `nvenc_error`.
  - Automatic encoding prefers ready `h264_nvenc`, then falls back to `libx264`.
- Added `TrackerConfig.engine` and `OutputConfig.encoder_mode`, both defaulting
  to `auto`. Pydantic before-validators migrate legacy `use_mediapipe` and
  supported legacy `video_codec` values. The existing `use_mediapipe` and
  `video_codec` fields remain readable for existing callers.

## Tests and TDD evidence

1. RED: `& .\\.venv\\Scripts\\python.exe -m pytest tests/test_acceleration.py tests/test_config.py -q`
   failed during collection with `ModuleNotFoundError: No module named
   'autoclip.web.acceleration'`, as expected before the contract implementation.
2. A requirement conflict was clarified before implementation: the supplied
   explicit-NVENC test had no ready tracker although the documented resolver
   order is tracker-first. The approved resolution retained tracker-first and
   added a ready `mediapipe_cpu` fixture to that test.
3. RED after the first config implementation: the legacy MediaPipe migration
   test failed because its validator omitted `return migrated`.
4. GREEN focused: `& .\\.venv\\Scripts\\python.exe -m pytest tests/test_acceleration.py tests/test_config.py -q`
   completed with **33 passed**.
5. GREEN full suite: `& .\\.venv\\Scripts\\python.exe -m pytest -q`
   completed with **189 passed**. It emitted three pre-existing third-party
   FastAPI/Starlette deprecation warnings and no test failures.
6. `& .\\.venv\\Scripts\\python.exe -m compileall -q autoclip` exited 0.

## Files changed

- Created `autoclip/web/acceleration.py`
- Modified `autoclip/models/config.py`
- Created `tests/test_acceleration.py`
- Modified `tests/test_config.py`

## Self-review

- The literal IDs match the requested values verbatim.
- Resolver tests cover Windows CUDA preference, Ubuntu MediaPipe GPU preference,
  Ubuntu YuNet CUDA fallback, CPU-only MediaPipe, no ready engine, unavailable
  explicit GPU, explicit NVENC failure, explicit HEVC, and CPU encoder fallback.
- Legacy YAML migration covers both `use_mediapipe` values, default `auto`, all
  supported legacy codecs, and explicit `encoder_mode` precedence.

## Concerns

- No Git repository exists in this workspace, so no commit was created.
- The full suite has three dependency deprecation warnings unrelated to this
  task; all tests pass.

## Review fix round 1

### Changes

- Added distro-aware default platform detection. On Linux it reads
  `/etc/os-release` and reports `Ubuntu` when `ID=ubuntu` or `ID_LIKE` includes
  `ubuntu`; other platforms retain `platform.system()` unchanged. Explicit
  `platform` injection for tests remains supported.
- Both `AccelerationStatus()` and `AccelerationStatus.for_test()` now use that
  default detector when no platform is supplied.
- Added a regression proving tracker-first ordering: an unavailable explicit
  NVENC request with no ready tracker raises `no_tracker_engine` first.
- Added an end-to-end `load_config()` YAML fixture proving persisted
  `output.video_codec: hevc_nvenc` remains readable and migrates to
  `output.encoder_mode == "hevc_nvenc"`. The loader deep-merges raw YAML then
  constructs `AutoClipConfig`, so the Pydantic `OutputConfig` before-validator
  performs the migration in the actual load path.

### TDD and verification evidence

1. RED: the newly added focused tests produced the expected Ubuntu failure:
   default status reported `Windows`/`Linux` rather than `Ubuntu`; the initial
   YAML fixture had escaped rather than physical newlines and was corrected so
   it exercised an actual YAML document.
2. GREEN focused:
