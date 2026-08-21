# Task 4 report: SQLite persistence

## Status

COMPLETE. Additive SQLite persistence, migration, validation, metadata JSON boundary, and tracking cleanup are implemented.

## Changed files

- `autoclip/web/runtime_store.py`
- `autoclip/web/full_store.py`
- `tests/test_runtime_store.py`
- `tests/test_full_store.py`
- `.superpowers/sdd/2026-08-13-gpu-acceleration/task-4-report.md`

No Task 2 or Task 3 file was changed. No Git command was run because no Git root exists.

## RED

Command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_runtime_store.py tests/test_full_store.py -q
```

Output before production changes:

```text
collected 11 items

tests\test_runtime_store.py FFF                                          [ 27%]
tests\test_full_store.py FFFFFFFF                                        [100%]

FAILED tests/test_runtime_store.py::test_old_artifact_table_receives_empty_metadata
FAILED tests/test_runtime_store.py::test_artifact_metadata_round_trips_without_sharing_input_mapping
FAILED tests/test_runtime_store.py::test_artifact_rejects_unknown_or_cross_project_clip
FAILED tests/test_full_store.py::test_project_selection_defaults_to_auto_and_round_trips
FAILED tests/test_full_store.py::test_project_selection_rejects_unknown_project
FAILED tests/test_full_store.py::test_project_selection_rejects_invalid_engine_ids[bogus-auto]
FAILED tests/test_full_store.py::test_project_selection_rejects_invalid_engine_ids[auto-bogus]
FAILED tests/test_full_store.py::test_clip_tracking_resolution_replaces_verified_run
FAILED tests/test_full_store.py::test_clip_tracking_resolution_validates_clip_and_trajectory_ids
FAILED tests/test_full_store.py::test_model_acknowledgement_records_plan_source_and_utc_timestamp
FAILED tests/test_full_store.py::test_clear_tracking_data_removes_resolution_and_tracking_artifacts
============================= 11 failed in 0.37s ==============================
```

Representative expected failures:

```text
AttributeError: 'Artifact' object has no attribute 'metadata'
TypeError: RuntimeStore.save_artifact() got an unexpected keyword argument 'metadata'
AttributeError: 'FullStudioStore' object has no attribute 'get_project_acceleration'
AttributeError: 'FullStudioStore' object has no attribute 'save_clip_tracking_resolution'
AttributeError: 'FullStudioStore' object has no attribute 'save_model_acknowledgement'
```

## GREEN

Focused command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_runtime_store.py tests/test_full_store.py -q
```

Output:

```text
collected 11 items

tests\test_runtime_store.py ...                                          [ 27%]
tests\test_full_store.py ........                                        [100%]

============================= 11 passed in 0.37s ==============================
```

Consumer regression command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_web_pipeline.py tests/test_web_jobs.py tests/test_tracking_service.py tests/test_tracking_render_integration.py tests/test_full_studio_api.py tests/test_runtime_api.py -q
```

Output:

```text
collected 8 items

tests\test_web_pipeline.py .                                             [ 12%]
tests\test_web_jobs.py .                                                 [ 25%]
tests\test_tracking_service.py ..                                        [ 50%]
tests\test_tracking_render_integration.py .                              [ 62%]
tests\test_full_studio_api.py ..                                         [ 87%]
tests\test_runtime_api.py .                                              [100%]

======================== 8 passed, 3 warnings in 2.34s ========================
```

Warnings are pre-existing Starlette deprecations. Syntax compilation also exited 0:

```powershell
.\.venv\Scripts\python.exe -m compileall -q autoclip\web\runtime_store.py autoclip\web\full_store.py tests\test_runtime_store.py tests\test_full_store.py
```

## Implementation

- Migrates legacy `artifacts` tables using `PRAGMA table_info` and an additive `metadata` column.
- Adds `project_acceleration`, `clip_tracking_resolutions`, and `model_acknowledgements` using `CREATE TABLE IF NOT EXISTS`.
- Persists default and selected tracker/encoder IDs with UTC timestamps.
- Upserts verified clip resolution, validates clip/trajectory relationships, and replaces prior runs.
- Saves model-plan source/license acknowledgement with UTC timestamp.
- Serializes and parses artifact metadata only in `RuntimeStore`; JSON round-trip prevents shared mutable input state.
- Clears preview/trajectory artifacts and clip resolution together with other stale tracking data.

## Self-review

- Every requested behavior has a failing-before/passing-after test.
- Unknown project/clip, invalid stable engine IDs, missing/wrong trajectory artifact, and cross-project clip cases are covered.
- Existing callers remain compatible because artifact metadata is optional and defaults to `{}`.
- Migration is idempotent for both new and pre-acceleration databases.
- No media/model route was added; stored paths remain private.

## Concerns

- `ruff` and `mypy` executables are absent from the current venv. `python -m ruff` reports `No module named ruff`; syntax compilation and pytest verification passed.

## Review fix round 1/5

Status: COMPLETE.

Finding verified: trajectory ownership was read in one SQLite connection, then the resolution was upserted in another. `clear_tracking_data()` could delete the trajectory after validation and before the upsert, leaving a dangling `trajectory_artifact_id`.

Fix:

- `save_clip_tracking_resolution()` now starts `BEGIN IMMEDIATE` and performs trajectory validation, resolution upsert, and saved-row readback in one connection/transaction.
- No process-global lock was introduced. SQLite serializes the competing cleanup write; cleanup either completes before validation (save rejects the missing artifact) or after the committed upsert (cleanup deletes both artifact and resolution).
- Added a deterministic connection-proxy test. It fully consumes the validation SELECT, then makes a second `timeout=0` SQLite connection attempt the interleaving delete. RED proves the delete originally succeeded; GREEN proves the reserved write lock rejects it as `database is locked` until commit.
- Added persistence proof by reopening the store and querying `model_acknowledgements`.
- Added rejection coverage for a valid tracking trajectory owned by another clip/project.

RED command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_runtime_store.py tests/test_full_store.py -q
```

RED output:

```text
collected 14 items

tests\test_runtime_store.py ...                                          [ 21%]
tests\test_full_store.py .......F...                                     [100%]

FAILED tests/test_full_store.py::test_clip_tracking_resolution_locks_validation_and_upsert_transaction
E   assert False is True
======================== 1 failed, 13 passed in 0.57s =========================
```

GREEN command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_runtime_store.py tests/test_full_store.py -q
```

GREEN output:

```text
collected 14 items

tests\test_runtime_store.py ...                                          [ 21%]
tests\test_full_store.py ...........                                     [100%]

============================= 14 passed in 0.48s ==============================
```

Consumer regression output:

```text
collected 8 items
======================== 8 passed, 3 warnings in 2.51s ========================
```

Syntax compilation exited 0. Warnings remain the same pre-existing Starlette deprecations. No Task 2/3 files or Git state were touched.
