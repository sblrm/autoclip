### Task 4: SQLite persistence for selections, runs, acknowledgements, and metadata

**Files:**

- Modify: `autoclip/web/runtime_store.py`
- Modify: `autoclip/web/full_store.py`
- Test: `tests/test_runtime_store.py`
- Test: `tests/test_full_store.py`

**Interfaces:**

- Consumes: `AccelerationSelection`, `ResolvedAcceleration`, `ModelPlan`, artifact metadata.
- Produces: `ProjectAcceleration`, `ClipTrackingResolution`, `ModelAcknowledgement`, metadata-bearing `Artifact`.

- [ ] **Step 1: Write failing round-trip and migration tests**

```python
def test_project_selection_defaults_to_auto_and_round_trips(store: FullStudioStore) -> None:
    project = store.create_from_url("https://example.test/video.mp4")

    assert store.get_project_acceleration(project.id).tracker_engine == "auto"
    saved = store.set_project_acceleration(project.id, tracker_engine="yunet_cuda", encoder_mode="h264_nvenc")
    assert saved.tracker_engine == "yunet_cuda"
    assert store.get_project_acceleration(project.id).encoder_mode == "h264_nvenc"


def test_old_artifact_table_receives_empty_metadata(tmp_path: Path) -> None:
    create_pre_acceleration_database(tmp_path / "studio.sqlite3")
    store = FullStudioStore(tmp_path / "projects")

    assert store.list_artifacts("project-1")[0].metadata == {}
```

- [ ] **Step 2: Run test to verify failure**

Run: `.\\.venv\\Scripts\\python.exe -m pytest tests/test_runtime_store.py tests/test_full_store.py -q`  
Expected: FAIL because new data records/migration do not exist.

- [ ] **Step 3: Add additive schema and store methods**

```python
@dataclass(frozen=True)
class ProjectAcceleration:
    project_id: str
    tracker_engine: TrackerEngine
    encoder_mode: EncoderMode
    updated_at: str


@dataclass(frozen=True)
class ClipTrackingResolution:
    clip_id: str
    tracker_engine: TrackerEngine
    provider: str
    model_id: str | None
    trajectory_artifact_id: str | None
    verified_at: str
```

Create `project_acceleration`, `clip_tracking_resolutions`, `model_acknowledgements` with `CREATE TABLE IF NOT EXISTS`. Use `PRAGMA table_info(artifacts)` then add `metadata TEXT NOT NULL DEFAULT '{}'` only if absent. Parse/serialize metadata JSON in `RuntimeStore` only.

Implement:

```python
def get_project_acceleration(self, project_id: str) -> ProjectAcceleration: ...
def set_project_acceleration(self, project_id: str, *, tracker_engine: TrackerEngine, encoder_mode: EncoderMode) -> ProjectAcceleration: ...
def save_clip_tracking_resolution(self, clip_id: str, resolution: ResolvedAcceleration, trajectory_artifact_id: str | None) -> ClipTrackingResolution: ...
def get_clip_tracking_resolution(self, clip_id: str) -> ClipTrackingResolution | None: ...
def save_model_acknowledgement(self, plan: ModelPlan) -> ModelAcknowledgement: ...
def save_artifact(self, project_id: str, kind: str, path: Path, clip_id: str | None = None, metadata: Mapping[str, Any] | None = None) -> Artifact: ...
```

First project-selection read creates `auto/auto`. `clear_tracking_data` removes stale preview/trajectory artifacts and clip resolution. Paths remain private: no model media route.

- [ ] **Step 4: Add invalid-ID and artifact coverage**

Test unknown project/clip, bad IDs, acknowledgement timestamp/source, resolution replacement, metadata round-trip, trajectory removal clearing resolution. Run:

```powershell
.\\.venv\\Scripts\\python.exe -m pytest tests/test_runtime_store.py tests/test_full_store.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit when repository exists**

```powershell
git add autoclip/web/runtime_store.py autoclip/web/full_store.py tests/test_runtime_store.py tests/test_full_store.py
git commit -m "feat: persist acceleration selections and metadata"
```

No Git root. Do not initialize/reset one.
