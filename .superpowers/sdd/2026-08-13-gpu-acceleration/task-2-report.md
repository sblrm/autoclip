# Task 2 report: pinned model catalog and checksum-safe manager

## Scope delivered

- Added immutable `ModelPlan` catalog in `autoclip/web/model_catalog.py`.
  - Pins YuNet 2023mar URL, SHA-256, size, MIT license, and local destination.
  - Pins the two InsightFace archive plans, exact archive member paths, and
    non-commercial research-only acknowledgement requirements.
- Added `ModelManager` and `InstalledModel` in `autoclip/web/model_manager.py`.
  - Accepts only `plan_id`, `acknowledged`, and a progress reporter; it has no
    caller-supplied URL or destination input.
  - Defaults local storage to `~/.autoclip/models`.
  - Streams catalog-owned downloads to `<plan-id>.part`, hashing and counting
    bytes; checksum/size failures delete partial artifacts.
  - Validates an existing raw model cache by size and SHA-256.
  - Atomically replaces final model files only after validation.
  - Extracts only the pinned archive member, rejects absolute, traversal, and
    symlink zip members, and removes temporary archives/outputs on all exits.
- Added deterministic tests in `tests/test_model_manager.py`; no model files
  are fetched from network.

## TDD record

### RED

Command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_model_manager.py -q
```

Initial result before production modules existed:

```text
ModuleNotFoundError: No module named 'autoclip.web.model_manager'
```

This was expected missing-behavior failure after adding catalog/download tests.

### GREEN

First implementation run found one expected classification mismatch:

```text
8 passed, 1 failed
ModelSizeError: model_size_error: plan_id=yunet_2023mar
```

Cause: a short corrupt payload was checked for final size before checksum.
Controller corrected only verification order in `_download_verified`: SHA-256
comparison now precedes final short-stream size comparison. This preserves the
required `FakeDownloader(b"wrong") -> ModelChecksumError` contract.

Fresh final focused/adjacent command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_model_manager.py tests/test_acceleration.py -q
.\.venv\Scripts\python.exe -m compileall autoclip\web\model_catalog.py autoclip\web\model_manager.py
```

Output:

```text
18 passed in 0.12s
```

`compileall` exited 0 with no errors.

## Full-suite verification

Command:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Result: `212 passed, 12 failed, 3 warnings in 7.71s`.

All Task 2 tests passed. Failures are outside Task 2 files and concern absent
pre-existing APIs in `MediaPipeTasksDetector`, `FullStudioStore`, and
`RuntimeStore` (`delegate`, acceleration store methods, and artifact metadata
methods). No Task 2 traceback appears in full-suite failures.

## Changed files

- `autoclip/web/model_catalog.py` (new)
- `autoclip/web/model_manager.py` (new)
- `tests/test_model_manager.py` (new)
- `.superpowers/sdd/2026-08-13-gpu-acceleration/task-2-report.md` (new)

## Self-review

- Catalog data matches exact plan IDs, URLs, sizes, SHA-256 values, and archive
  members in Task 2 brief.
- `ModelPlan` is frozen and catalog mapping is read-only.
- Download code uses only catalog URLs; installer interface admits no external
  URL/model-path parameters.
- Cache hit verifies raw model digest and does not invoke downloader.
- Partial download/archive/extraction output cleanup covers checksum, size,
  zip-validation, missing-member, and extraction errors.
- Zip input checks all member names before extraction, rejects unsafe names,
  and extracts no unlisted file.
- No detector/session/HTTP route work added. No Git repository was initialized
  and no commit was made.

## Concern

Full project suite has 12 unrelated failures described above; not modified to
avoid scope expansion.

## Review fix round 1: archive cache manifest

### Root cause

Archive plans pin checksum and size for their downloaded ZIP. The prior cache
path checked the extracted `.onnx` against those ZIP values, so archive model
cache validation always failed and a second installation downloaded again.

### RED

Added archive cache-hit and manifest identity tests. Before production change:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_model_manager.py -q
```

Output:

```text
2 failed, 8 passed in 0.15s
```

Failures proved both defects: second archive install returned
`cached=False`, and no `<destination>.autoclip.json` manifest existed.

### GREEN

- Archive installation now atomically writes an identity-bound manifest with
  `plan_id`, `source_url`, `archive_sha256`, `archive_bytes`, and
  `destination_relative_path`.
- Archive cache hits require both a safe regular extracted file and a safe,
  matching manifest. A malformed/tampered manifest forces a verified
  re-download.
- Direct model cache validation remains size/SHA-256 verification against the
  pinned raw-model plan.
- Archive extraction/manifest failure removes both destination and sidecar;
  temporary archive/output cleanup remains unchanged.

Final commands:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_model_manager.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_model_manager.py tests/test_acceleration.py -q
.\.venv\Scripts\python.exe -m compileall autoclip\web\model_catalog.py autoclip\web\model_manager.py
.\.venv\Scripts\python.exe -m pytest -q
```

Evidence:

```text
tests/test_model_manager.py: 10 passed in 0.13s
focused model + acceleration: 19 passed in 0.13s
compileall: exit 0
full suite: 213 passed, 12 failed, 3 warnings in 13.22s
```

Full-suite failures remain outside Task 2: one missing detector `delegate`
argument, eight missing `FullStudioStore` methods, and three missing/incorrect
`RuntimeStore` artifact contracts. No Task 2 traceback appears.

### Review self-check

- Archive raw ZIP stays fully size/SHA-256 verified before extraction.
- Archive cache never treats an extracted model as though it were the ZIP.
- Manifest binds cache entry to exact pinned plan identity, source, archive
  digest, byte count, and extraction destination.
- Cache accepts no symlink for archive model or manifest.
- New test performs real second archive `install()` and proves downloader has
  exactly one call; it then tampers sidecar and proves verified re-download.

## Review fix round 2: extracted payload integrity

### Root cause

Round 1 manifest bound a cached archive installation to pinned ZIP identity,
but did not bind it to bytes in the extracted `.onnx`. Replacing extracted
payload while retaining sidecar made cache validation return a false hit.

### RED

Added regression that installs test archive, writes `b"tampered payload"` to
the extracted destination without changing sidecar, then installs again.

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_model_manager.py -q
```

Output before implementation:

```text
1 failed, 10 passed in 0.15s
AssertionError: assert True is False
```

The second installation reported `cached=True`, reproducing integrity gap.

### GREEN

- After verified archive extraction, manager computes extracted file byte count
  and SHA-256, then writes both atomically in manifest as `extracted_bytes` and
  `extracted_sha256`.
- Archive cache validation now compares exact pinned ZIP identity fields and
  fresh extracted-file size/SHA-256 against manifest.
- Tampered extracted payload now triggers re-download/re-extraction while an
  untouched valid archive install remains a cache hit.
- Direct-model cache behavior remains pinned raw file size/SHA-256 validation.

First implementation test exposed an omitted cache-validator call-site
argument (`TypeError` for missing `destination`); corrected before final
verification.

Final commands and evidence:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_model_manager.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_model_manager.py tests/test_acceleration.py -q
.\.venv\Scripts\python.exe -m compileall autoclip\web\model_catalog.py autoclip\web\model_manager.py
```

```text
tests/test_model_manager.py: 11 passed in 0.12s
focused model + acceleration: 20 passed in 0.15s
compileall: exit 0
```

### Review self-check

- Cache hit requires safe regular extracted file, safe regular manifest, full
  pinned archive identity, and extracted payload size/SHA-256 match.
- Payload mutation with untouched manifest is covered by deterministic fake
  downloader regression; reinstalled output equals original archive member.
- ZIP download checksum/size validation still runs before extraction.
