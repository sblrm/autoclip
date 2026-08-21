# Task 6 report: safe acceleration HTTP API, setup jobs, precise status

## Result

Implemented fixed acceleration status/plans/recheck/install/selection APIs on the full studio server while preserving the existing `/api/setup/*` surface in `usable_studio.py`.

Key behavior:

- Browser input is limited by a `Literal` plan ID and `extra="forbid"`; no URL, package, destination, or command can be supplied.
- `onnxruntime_cuda_128` uses one server-owned `InstallPlan` pinned to `onnxruntime-gpu[cuda,cudnn]==1.26.0`.
- Model IDs use `MODEL_PLANS` and `ModelManager.install`; they never pass through the command runner.
- Research acknowledgement is persisted before the model job is submitted.
- All acceleration installs use durable `setup:acceleration:<plan_id>` jobs on the existing `SerialJobRunner`.
- Project acceleration choices are live-resolved before persistence and return 409 for `nvenc_error` or `no_tracker_engine`.
- Project detail includes saved `acceleration` and each clip's `tracking_resolution`.
- Runtime health retains all legacy fields and adds verified `acceleration` evidence.
- Setup components now expose optional `provider`, `model_id`, `probe_detail`, and `error_code`, with separate rows for Whisper, PyTorch, ONNX Runtime CUDA, MediaPipe CPU/GPU, YuNet CPU/CUDA, and FFmpeg encoders.
- A working `2.11.0+cu128` PyTorch runtime is rejected as already active instead of being reinstalled. Legacy fallback installation now targets the CUDA 12.8 index.
- ONNX Runtime CUDA readiness requires the actual `CUDAExecutionProvider` after `preload_dlls()`; a CPU-only runtime is not labeled CUDA-ready.

## TDD evidence

### RED

Command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_acceleration_api.py tests/test_setup_manager.py tests/test_usable_studio.py -q
```

Observed before production changes:

- `11 failed, 3 passed`
- Acceleration routes returned 404.
- `onnxruntime_cuda_128` was unsupported.
- working cu128 PyTorch was not preserved.
- `SetupManager` did not accept verified acceleration status.

Additional precision RED:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_setup_manager.py::test_cpu_only_onnxruntime_is_not_reported_as_cuda_ready -q
```

Observed: expected `unsupported`, received `ready`.

### GREEN

Initial focused command produced `14 passed`. After the ONNX provider precision test, `tests/test_setup_manager.py` produced `6 passed`.

Required Task 6 command after all changes:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_acceleration_api.py tests/test_setup_manager.py tests/test_usable_studio.py tests/test_cli_web.py -q
```

Observed: `16 passed, 1 warning in 3.28s`.

Full verification:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Observed: `257 passed, 3 warnings in 7.94s`.

Compile verification:

```powershell
.\.venv\Scripts\python.exe -m compileall -q autoclip tests/test_acceleration_api.py tests/test_setup_manager.py tests/test_usable_studio.py
```

Observed: `compileall: PASS`.

## Files

- `autoclip/web/setup_manager.py`
- `autoclip/web/studio_server.py`
- `autoclip/web/usable_studio.py`
- `tests/test_acceleration_api.py`
- `tests/test_setup_manager.py`
- `tests/test_usable_studio.py`
- `.superpowers/sdd/2026-08-13-gpu-acceleration/task-6-report.md`

## Self-review

- Safety: public plan payloads omit commands and source URLs; request models reject unknown IDs and extra fields.
- Execution boundary: only the fixed ONNX package plan reaches `SetupManager.install`; pinned models use checksum-verifying `ModelManager`.
- Ordering: acknowledgement write occurs before job creation/submission, so downloader start cannot precede durable consent.
- Persistence: acceleration jobs use the existing SQLite jobs table and serial worker; exceptions remain durable failed jobs.
- Compatibility: legacy setup routes and response fields remain; full legacy and new test suite passes.
- Accuracy: ONNX CUDA, tracker providers/models, and encoder availability are reported independently instead of inferred from a generic GPU badge.

## Concerns

- Ruff is declared in `pyproject.toml` but is not installed in this `.venv`; `.\.venv\Scripts\python.exe -m ruff ...` returned `No module named ruff`. No dependency installation was attempted.
- Test output contains existing Starlette/FastAPI deprecation warnings (`httpx` TestClient bridge and HTTP 422 constant). No Task 6 failures or warnings from application code were observed.
- No Git commands or changes were made.
