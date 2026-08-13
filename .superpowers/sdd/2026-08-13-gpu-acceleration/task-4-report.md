# Task 4 report: SQLite persistence

## Status

BLOCKED. RED tests were added and verified, but the filesystem sandbox rejects every `apply_patch` update to the two existing production files. Per task brief, no shell-write workaround was used.

## Changed files

- `tests/test_runtime_store.py` (new)
- `tests/test_full_store.py` (new)
- `.superpowers/sdd/2026-08-13-gpu-acceleration/task-4-report.md` (new)

No production file was changed.

## RED

Command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_runtime_store.py tests/test_full_store.py -q
```

Output:

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

Not run: production implementation could not be applied.

## Exact blocker

Absolute-path `apply_patch` against `autoclip/web/runtime_store.py`:

```text
apply_patch verification failed: Failed to read file to update G:\App\AutoClip\autoclip\web\runtime_store.py: fs sandbox helper failed with status exit code: 1: windows sandbox failed: helper_unknown_error: setup refresh had errors
```

Relative-path retry against `autoclip/web/full_store.py`:

```text
apply_patch verification failed: Failed to read file to update G:\App\AutoClip\autoclip\web\full_store.py: fs sandbox helper failed with status exit code: 1: windows sandbox failed: helper_unknown_error: setup refresh had errors
```

## Self-review

- Tests cover additive artifact migration, metadata round-trip/copy isolation, project/clip relationship validation, default and persisted selection, invalid stable IDs, tracking-resolution replacement, trajectory validation, UTC acknowledgement provenance, and cleanup behavior.
- RED failures come from missing requested behavior, not test syntax/import errors.
- No Task 2 or Task 3 files were changed.
- No Git command was run because no Git root exists.

## Concerns

- Existing-file sandbox failure prevents all required production work and GREEN verification.
- `ModelAcknowledgement` field names still require implementation choice; tests currently specify `plan_id`, `source_url`, `license`, and `acknowledged_at`, matching plan terminology and provenance requirements.
