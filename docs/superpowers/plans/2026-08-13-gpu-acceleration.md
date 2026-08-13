# GPU Acceleration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add trustworthy, user-selectable NVIDIA GPU face tracking and NVENC export while keeping CPU behavior explicit, local, resumable, and compatible with existing CLI configuration.

**Architecture:** A new acceleration domain owns live platform probes, fixed install/model plans, and deterministic engine/encoder resolution. Tracking receives one resolved detector per clip, writes its identity with the saved trajectory, and uses that trajectory for preview and final export. FastAPI only accepts fixed identifiers; Setup Center and studio inspector consume same contract.

**Tech Stack:** Python, FastAPI, SQLite, FFmpeg, OpenCV, MediaPipe Tasks, ONNX Runtime CUDA, React, TypeScript, Vite, Vitest, pytest.

## Global Constraints

- NVIDIA support only on Windows and Ubuntu. Other hardware reports CPU or unsupported, never GPU.
- Tracker engines: `auto`, `mediapipe_cpu`, `mediapipe_gpu`, `yunet_cpu`, `yunet_cuda`, `scrfd_cpu`, `scrfd_cuda`, `retinaface_cpu`, `retinaface_cuda`.
- Encoder modes: `auto`, `h264_nvenc`, `hevc_nvenc`, `libx264`. Runtime states: `ready`, `missing`, `unsupported`, `failed`, `requires_acknowledgement`.
- Auto tracker order: verified Ubuntu MediaPipe GPU, verified NVIDIA YuNet CUDA, MediaPipe CPU, YuNet CPU, structured `no_tracker_engine` error.
- Auto encoder selects verified `h264_nvenc` then `libx264`. Explicit NVENC never falls back; it returns `nvenc_error`.
- A GPU engine is ready only after detector/session construction and one real inference. Hardware presence, package import, CUDA Toolkit, or FFmpeg listing alone are insufficient.
- MediaPipe GPU is Ubuntu-only and must use `BaseOptions(delegate=Delegate.GPU)` with FaceDetector VIDEO-mode inference.
- No HTTP body supplies shell commands, package IDs, URLs, provider lists, model IDs, or file paths.
- Models live under `~/.autoclip/models`. Downloads are user-triggered, allow-listed, atomic, byte-count and SHA-256 checked. No recognition embeddings are created/stored.
- Commercial-safe default: YuNet 2023mar, MIT, 232589 bytes, SHA-256 `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4`, source `https://github.com/opencv/opencv_zoo/raw/4.10.0/models/face_detection_yunet/face_detection_yunet_2023mar.onnx`.
- Research-only InsightFace plans require acknowledgement: buffalo_m RetinaFace, 275951529 bytes, SHA-256 `d98264bd8f2dc75cbc2ddce2a14e636e02bb857b3051c234b737bf3b614edca9`; antelopev2 SCRFD, 360662982 bytes, SHA-256 `8e182f14fc6e80b3bfa375b33eb6cff7ee05d8ef7633e738d1c89021dcf0c5c5`. Both use InsightFace `v0.7` GitHub release URLs. InsightFace code is MIT; pretrained assets are non-commercial research only.
- Legacy `use_mediapipe: true` maps to `mediapipe_cpu`, false maps to `auto`. New projects/configs default both tracker and encoder to `auto`.
- Subject lock, gaps, hold-then-ease crop, approval gate, and project-owned artifact serving stay unchanged.
- User current runtime is PyTorch `2.11.0+cu128` and RTX 5070. CUDA 12.8 ONNX Runtime plan must verify a YuNet CUDA inference and must not require CUDA Toolkit installation.

---

## File Structure

| Path | Responsibility |
|---|---|
| `autoclip/web/acceleration.py` | Stable IDs, probe contract, resolver, strict errors. |
| `autoclip/web/model_catalog.py` | Immutable model/install allow-list and license rules. |
| `autoclip/web/model_manager.py` | Atomic model download, validation, extraction, cache. |
| `autoclip/web/detectors.py` | MediaPipe, YuNet, SCRFD, RetinaFace adapters behind one VIDEO detector interface. |
| `autoclip/web/acceleration_manager.py` | Live runtime, model, provider, and FFmpeg checks. |
| `autoclip/web/runtime_store.py` | SQLite acceleration selection, runs, acknowledgements, artifact metadata. |
| `autoclip/web/rendering.py` | Resolved detector, trajectory identity, preview/export metadata. |
| `autoclip/utils/ffmpeg.py` | NVENC listing, smoke test, encoder arguments, strict resolution. |
| `autoclip/core/tracker.py` | Face crop uses supplied `VideoEncoding`. |
| `autoclip/web/studio_server.py` | Safe API, selection, status, jobs, enforcement. |
| `autoclip/web/setup_manager.py` | Per-component setup status and fixed CUDA plans. |
| `autoclip/models/config.py` | Backward-compatible CLI config. |
| `web/src/api.ts` | Shared frontend contracts/client. |
| `web/ux/AccelerationCenter.tsx` | Reusable bilingual GPU controls. |
| `web/ux/SetupStudio.tsx` and `web/src/App.tsx` | Setup and inspector integration. |

### Task 1: Stable acceleration contracts and config migration

**Files:**

- Create: `autoclip/web/acceleration.py`
- Modify: `autoclip/models/config.py`
- Test: `tests/test_acceleration.py`
- Test: `tests/test_config.py`

**Interfaces:**

- Consumes: local probe results.
- Produces: `TrackerEngine`, `EncoderMode`, `RuntimeState`, `AccelerationSelection`, `AccelerationStatus`, `ResolvedAcceleration`, `resolve()`.

- [ ] **Step 1: Write failing resolver/config tests**

```python
import pytest

from autoclip.models.config import OutputConfig, TrackerConfig
from autoclip.web.acceleration import AccelerationSelection, EncoderUnavailable


def test_auto_prefers_verified_yunet_cuda_on_windows() -> None:
    status = AccelerationStatus.for_test(
        platform="Windows",
        engines={"yunet_cuda": ("ready", "CUDAExecutionProvider")},
        encoders={"h264_nvenc": "ready"},
    )

    resolved = status.resolve(AccelerationSelection())

    assert resolved.tracker_engine == "yunet_cuda"
    assert resolved.encoder_mode == "h264_nvenc"
    assert resolved.provider == "CUDAExecutionProvider"


def test_explicit_nvenc_never_becomes_cpu() -> None:
    status = AccelerationStatus.for_test(encoders={"h264_nvenc": "failed"})

    with pytest.raises(EncoderUnavailable, match="nvenc_error"):
        status.resolve(AccelerationSelection(encoder_mode="h264_nvenc"))


def test_legacy_mediapipe_yaml_remains_readable() -> None:
    assert TrackerConfig.model_validate({"use_mediapipe": True}).engine == "mediapipe_cpu"
    assert TrackerConfig.model_validate({"use_mediapipe": False}).engine == "auto"
    assert TrackerConfig().engine == "auto"
    assert OutputConfig().encoder_mode == "auto"
```

- [ ] **Step 2: Run tests to verify expected failure**

Run: `python -m pytest tests/test_acceleration.py tests/test_config.py -q`  
Expected: FAIL because acceleration contracts and new config fields do not exist.

- [ ] **Step 3: Implement literal IDs, immutable objects, and resolver**

```python
TrackerEngine = Literal[
    "auto", "mediapipe_cpu", "mediapipe_gpu", "yunet_cpu", "yunet_cuda",
    "scrfd_cpu", "scrfd_cuda", "retinaface_cpu", "retinaface_cuda",
]
EncoderMode = Literal["auto", "h264_nvenc", "hevc_nvenc", "libx264"]
RuntimeState = Literal["ready", "missing", "unsupported", "failed", "requires_acknowledgement"]


@dataclass(frozen=True)
class AccelerationSelection:
    tracker_engine: TrackerEngine = "auto"
    encoder_mode: EncoderMode = "auto"


@dataclass(frozen=True)
class ResolvedAcceleration:
    tracker_engine: TrackerEngine
    encoder_mode: EncoderMode
    provider: str
    model_id: str | None


class EncoderUnavailable(ValueError):
    error_code = "nvenc_error"
```

Implement `AccelerationStatus.resolve()` exactly:

1. explicit tracker requires state `ready` or raises `TrackerUnavailable` with engine/state/probe reason;
2. auto chooses Ubuntu `mediapipe_gpu`, then `yunet_cuda`, `mediapipe_cpu`, `yunet_cpu`, otherwise `TrackerUnavailable("no_tracker_engine")`;
3. explicit encoder requires `ready` or raises `EncoderUnavailable("nvenc_error: ...")`;
4. auto chooses ready `h264_nvenc`, else `libx264`.

Add `TrackerConfig.engine` and `OutputConfig.encoder_mode` with default `auto`. Use Pydantic `model_validator(mode="before")` so persisted YAML maps old `use_mediapipe` exactly as test says. If old `video_codec` is `libx264`, `h264_nvenc`, or `hevc_nvenc` and no `encoder_mode` exists, map it into encoder mode. Keep `video_codec` field for old callers.

- [ ] **Step 4: Add complete selection matrix and pass it**

Add Ubuntu MediaPipe GPU preference, Ubuntu CUDA YuNet fallback, CPU-only MediaPipe, no engine, unavailable explicit GPU, explicit HEVC, and CPU encoder fallback cases. Run:

```powershell
python -m pytest tests/test_acceleration.py tests/test_config.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit when repository exists**

```powershell
git add autoclip/web/acceleration.py autoclip/models/config.py tests/test_acceleration.py tests/test_config.py
git commit -m "feat: add acceleration resolver contracts"
```

Current workspace has no Git root. Do not initialize/reset one only to record this step.

### Task 2: Pinned model catalog and checksum-safe manager

**Files:**

- Create: `autoclip/web/model_catalog.py`
- Create: `autoclip/web/model_manager.py`
- Test: `tests/test_model_manager.py`

**Interfaces:**

- Consumes: server-selected `plan_id` and `acknowledged: bool`.
- Produces: `ModelPlan`, `MODEL_PLANS`, `InstalledModel`, `ModelManager.install(plan_id, acknowledged, report)`.

- [ ] **Step 1: Write failing catalog/download tests**

```python
def test_yunet_plan_is_fixed_and_commercial_safe() -> None:
    plan = MODEL_PLANS["yunet_2023mar"]

    assert plan.research_only is False
    assert plan.sha256 == "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"
    assert plan.destination_relative_path == "yunet/face_detection_yunet_2023mar.onnx"


def test_research_model_requires_acknowledgement(tmp_path: Path) -> None:
    manager = ModelManager(tmp_path, downloader=FakeDownloader())

    with pytest.raises(ResearchAcknowledgementRequired):
        manager.install("insightface_buffalo_m_retinaface", False, lambda *_: None)


def test_bad_checksum_removes_partial_file(tmp_path: Path) -> None:
    manager = ModelManager(tmp_path, downloader=FakeDownloader(b"wrong"))

    with pytest.raises(ModelChecksumError):
        manager.install("yunet_2023mar", False, lambda *_: None)

    assert not list(tmp_path.rglob("*.part"))
    assert not (tmp_path / "yunet" / "face_detection_yunet_2023mar.onnx").exists()
```

- [ ] **Step 2: Run test to verify failure**

Run: `python -m pytest tests/test_model_manager.py -q`  
Expected: FAIL because catalog/manager are absent.

- [ ] **Step 3: Implement immutable allow-list and atomic operations**

```python
@dataclass(frozen=True)
class ModelPlan:
    id: str
    label: str
    source_url: str
    sha256: str
    bytes: int
    license: str
    research_only: bool
    destination_relative_path: str
    archive_member: str | None = None


MODEL_PLANS = {
    "yunet_2023mar": ModelPlan(
        id="yunet_2023mar",
        label="YuNet 2023mar",
        source_url="https://github.com/opencv/opencv_zoo/raw/4.10.0/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        sha256="8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
        bytes=232589,
        license="MIT",
        research_only=False,
        destination_relative_path="yunet/face_detection_yunet_2023mar.onnx",
    ),
}
```

Add:

```python
"insightface_buffalo_m_retinaface": ModelPlan(
    "insightface_buffalo_m_retinaface", "InsightFace buffalo_m RetinaFace detector",
    "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_m.zip",
    "d98264bd8f2dc75cbc2ddce2a14e636e02bb857b3051c234b737bf3b614edca9",
    275951529, "Non-commercial research only (InsightFace pretrained asset)", True,
    "insightface/buffalo_m/det_2.5g.onnx", "det_2.5g.onnx",
),
"insightface_antelopev2_scrfd": ModelPlan(
    "insightface_antelopev2_scrfd", "InsightFace antelopev2 SCRFD detector",
    "https://github.com/deepinsight/insightface/releases/download/v0.7/antelopev2.zip",
    "8e182f14fc6e80b3bfa375b33eb6cff7ee05d8ef7633e738d1c89021dcf0c5c5",
    360662982, "Non-commercial research only (InsightFace pretrained asset)", True,
    "insightface/antelopev2/scrfd_10g_bnkps.onnx", "scrfd_10g_bnkps.onnx",
),
```

Download to `<models_root>/<plan-id>.part`, stream count/SHA-256, then compare count and digest before extraction. Only extract listed archive member. Reject absolute and parent-traversal zip names. Atomically replace detector only after verification. Delete temporary archive/partial output on success and failure. A valid existing destination is cache hit. Default root is `Path.home() / ".autoclip" / "models"`.

- [ ] **Step 4: Add error/cache/path-traversal cases**

Test unknown ID, no browser-supplied URL path, cached valid hash avoids downloader, acknowledgement succeeds, overlarge stream fails, malicious zip cannot escape root, and archive is discarded after extraction. Run:

```powershell
python -m pytest tests/test_model_manager.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit when repository exists**

```powershell
git add autoclip/web/model_catalog.py autoclip/web/model_manager.py tests/test_model_manager.py
git commit -m "feat: add verified face model installer"
```

### Task 3: Live runtime probes and strict detector adapters

**Files:**

- Create: `autoclip/web/detectors.py`
- Create: `autoclip/web/acceleration_manager.py`
- Modify: `autoclip/web/tracking.py`
- Test: `tests/test_detectors.py`
- Test: `tests/test_acceleration_manager.py`

**Interfaces:**

- Consumes: `ResolvedAcceleration`, cached detector model, BGR frame, monotonic millisecond timestamp.
- Produces: `VideoFaceDetector`, `DetectorFactory.create(resolution)`, `AccelerationManager.status()`.

- [ ] **Step 1: Write failing strict-provider/live-probe tests**

```python
def test_yunet_cuda_requests_cuda_and_no_cpu_provider() -> None:
    sessions = FakeSessionFactory(providers=("CUDAExecutionProvider",))
    detector = DetectorFactory(session_factory=sessions).create(
        ResolvedAcceleration("yunet_cuda", "libx264", "CUDAExecutionProvider", "yunet_2023mar")
    )

    assert sessions.requested_providers == ["CUDAExecutionProvider"]
    assert detector.engine == "yunet_cuda"


def test_mediapipe_gpu_probe_never_reports_cpu_as_gpu() -> None:
    status = AccelerationManager(probe=UbuntuProbe(), detector_factory=GpuFailingFactory()).status()
    capability = status.engine("mediapipe_gpu")

    assert capability.state == "failed"
    assert capability.provider != "CPU"


def test_detector_returns_normalized_centres() -> None:
    result = YuNetDecoder().decode(FIXTURE_OUTPUTS, source_width=640, source_height=360)

    assert result == [FaceObservation(cx=0.5, cy=0.5, confidence=0.95)]
```

- [ ] **Step 2: Run test to verify failure**

Run: `python -m pytest tests/test_detectors.py tests/test_acceleration_manager.py -q`  
Expected: FAIL because adapters and manager do not exist.

- [ ] **Step 3: Build one detector contract and four engine families**

```python
class VideoFaceDetector(Protocol):
    engine: TrackerEngine
    provider: str
    model_id: str | None

    def __enter__(self) -> "VideoFaceDetector": ...
    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None: ...
    def detect(self, frame_bgr: NDArray[np.uint8], timestamp_ms: int) -> list[FaceObservation]: ...


class DetectorFactory:
    def create(self, resolution: ResolvedAcceleration) -> VideoFaceDetector: ...
```

Refactor `MediaPipeTasksDetector` to accept an optional `mp.tasks.BaseOptions.Delegate` and pass it to `BaseOptions(model_asset_path=..., delegate=delegate)`. Keep `RunningMode.VIDEO` and `detect_for_video`. Offer GPU only when `platform.freedesktop_os_release()["ID"] == "ubuntu"`; create detector and infer one generated 320×320 BGR frame before ready.

Implement `YuNetOnnxDetector` with 320×320 letterboxed BGR-to-RGB float32 NCHW input, scale/padding reversal, YuNet box/score decode, IoU 0.3 NMS, and normalized/clamped `FaceObservation`. Order output by confidence descending then x/y ascending. Construct ORT as:

```python
onnxruntime.preload_dlls()
session = onnxruntime.InferenceSession(
    str(model_path),
    providers=["CUDAExecutionProvider"] if cuda else ["CPUExecutionProvider"],
)
if expected_provider not in session.get_providers():
    raise TrackerUnavailable(f"{engine} did not create {expected_provider}")
```

Do not supply CPU fallback provider for any `*_cuda` engine. Implement `InsightFaceOnnxDetector` for extraction-only detector ONNX files; it may use detector preprocessing/anchor decoder utilities but must not construct recognition models or persist embeddings.

- [ ] **Step 4: Implement full live capability states and pass tests**

`AccelerationManager` checks OS/distro, NVIDIA name/driver, PyTorch CUDA, `onnxruntime.get_available_providers()`, `preload_dlls()`, actual YuNet session/inference, MediaPipe CPU/GPU detection inference, and model cache/hash state. Tests must prove: model absent is `missing`; non-Ubuntu MediaPipe GPU is `unsupported`; CUDA session exception is `failed` with scrubbed detail; empty face result proves inference and is not fallback; explicit GPU cannot call CPU detector.

Run:

```powershell
python -m pytest tests/test_detectors.py tests/test_acceleration_manager.py tests/test_web_tracking.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit when repository exists**

```powershell
git add autoclip/web/detectors.py autoclip/web/acceleration_manager.py autoclip/web/tracking.py tests/test_detectors.py tests/test_acceleration_manager.py
git commit -m "feat: add verified face detector engines"
```

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

Run: `python -m pytest tests/test_runtime_store.py tests/test_full_store.py -q`  
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

Create `project_acceleration`, `clip_tracking_resolutions`, `model_acknowledgements` using `CREATE TABLE IF NOT EXISTS`. Use `PRAGMA table_info(artifacts)` and only then add `metadata TEXT NOT NULL DEFAULT '{}'`. Parse/serialize metadata JSON in `RuntimeStore` only.

Implement:

```python
def get_project_acceleration(self, project_id: str) -> ProjectAcceleration: ...
def set_project_acceleration(self, project_id: str, *, tracker_engine: TrackerEngine, encoder_mode: EncoderMode) -> ProjectAcceleration: ...
def save_clip_tracking_resolution(self, clip_id: str, resolution: ResolvedAcceleration, trajectory_artifact_id: str | None) -> ClipTrackingResolution: ...
def get_clip_tracking_resolution(self, clip_id: str) -> ClipTrackingResolution | None: ...
def save_model_acknowledgement(self, plan: ModelPlan) -> ModelAcknowledgement: ...
def save_artifact(self, project_id: str, kind: str, path: Path, clip_id: str | None = None, metadata: Mapping[str, Any] | None = None) -> Artifact: ...
```

First project-selection read creates `auto/auto` row. `clear_tracking_data` removes stale preview/trajectory artifacts and clip resolution. Paths remain private: no model media route.

- [ ] **Step 4: Add invalid-ID and artifact coverage**

Test unknown project/clip, bad IDs, acknowledgement timestamp/source, resolution replacement, metadata round-trip, and trajectory removal clearing resolution. Run:

```powershell
python -m pytest tests/test_runtime_store.py tests/test_full_store.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit when repository exists**

```powershell
git add autoclip/web/runtime_store.py autoclip/web/full_store.py tests/test_runtime_store.py tests/test_full_store.py
git commit -m "feat: persist acceleration selections and metadata"
```

### Task 5: NVENC checks and tracking render integration

**Files:**

- Modify: `autoclip/utils/ffmpeg.py`
- Modify: `autoclip/core/tracker.py`
- Modify: `autoclip/web/rendering.py`
- Test: `tests/test_nvenc.py`
- Test: `tests/test_tracking_render_integration.py`

**Interfaces:**

- Consumes: `EncoderMode`, encoder capability, saved `ClipTrackingResolution`.
- Produces: `VideoEncoding`, `list_video_encoders()`, `smoke_test_encoder()`, `resolve_video_encoding()`, metadata-bearing render artifacts.

- [ ] **Step 1: Write failing NVENC/no-fallback/metadata tests**

```python
def test_auto_selects_verified_h264_nvenc() -> None:
    encoding = resolve_video_encoding("auto", {"h264_nvenc": EncoderCapability.ready()})

    assert encoding.mode == "h264_nvenc"
    assert encoding.arguments == ["-c:v", "h264_nvenc", "-preset", "p5", "-cq", "23", "-b:v", "0"]


def test_explicit_nvenc_smoke_failure_stays_structured() -> None:
    with pytest.raises(EncoderUnavailable, match="nvenc_error"):
        resolve_video_encoding("h264_nvenc", {"h264_nvenc": EncoderCapability.failed("No NVENC capable devices found")})


def test_export_metadata_contains_encoder_and_detector(...) -> None:
    artifact = service.export_approved(clip.id, report)

    assert artifact.metadata["encoder_mode"] == "h264_nvenc"
    assert artifact.metadata["tracker_engine"] == "yunet_cuda"
```

- [ ] **Step 2: Run test to verify failure**

Run: `python -m pytest tests/test_nvenc.py tests/test_tracking_render_integration.py -q`  
Expected: FAIL because encoder capability/metadata are absent.

- [ ] **Step 3: Implement parse, smoke, and strict resolved FFmpeg arguments**

```python
@dataclass(frozen=True)
class VideoEncoding:
    mode: EncoderMode
    codec: str
    arguments: list[str]


def smoke_test_encoder(mode: Literal["h264_nvenc", "hevc_nvenc"], runner: CommandRunner) -> EncoderCapability:
    result = runner([
        "ffmpeg", "-hide_banner", "-y", "-f", "lavfi", "-i", "color=c=black:s=16x16:d=0.1",
        "-frames:v", "1", "-c:v", mode, "-f", "null", "-",
    ])
    return EncoderCapability.ready() if result.returncode == 0 else EncoderCapability.failed(result.output[-1000:])
```

Parse `ffmpeg -hide_banner -encoders` before smoke testing. Encoding argument choices:

- `libx264`: `["-c:v", "libx264", "-crf", "23", "-preset", "medium"]`;
- `h264_nvenc`: `["-c:v", "h264_nvenc", "-preset", "p5", "-cq", "23", "-b:v", "0"]`;
- `hevc_nvenc`: `["-c:v", "hevc_nvenc", "-preset", "p5", "-cq", "25", "-b:v", "0"]`.

`apply_face_crop` accepts `encoding: VideoEncoding` and appends exact arguments. Remove unconditional `libx264` while preserving AAC audio output.

- [ ] **Step 4: Save detector identity once and reuse trajectory**

At `detect_tracks`, load project selection, resolve status, create one detector, and save `ClipTrackingResolution`. Trajectory JSON must include tracker engine/provider/model. At preview/export, load saved resolution, resolve encoder, call cropper with `encoding`, and save:

```python
{
    "encoder_mode": encoding.mode,
    "encoder": encoding.codec,
    "tracker_engine": resolution.tracker_engine,
    "provider": resolution.provider,
    "model_id": resolution.model_id,
    "trajectory_artifact_id": trajectory_artifact.id,
}
```

Preview/export may use different dimensions but never rerun detection/change selected track/change detector identity. Missing resolution is job error, never centre crop.

- [ ] **Step 5: Run and commit**

```powershell
python -m pytest tests/test_nvenc.py tests/test_tracking_render_integration.py tests/test_tracking_service.py tests/test_web_tracking.py -q
git add autoclip/utils/ffmpeg.py autoclip/core/tracker.py autoclip/web/rendering.py tests/test_nvenc.py tests/test_tracking_render_integration.py
git commit -m "feat: add verified NVENC tracked export"
```

Expected tests: PASS. Run Git commands only if repository exists.

### Task 6: Safe HTTP API, setup jobs, and precise setup status

**Files:**

- Modify: `autoclip/web/setup_manager.py`
- Modify: `autoclip/web/studio_server.py`
- Modify: `autoclip/web/usable_studio.py`
- Create: `tests/test_acceleration_api.py`
- Modify: `tests/test_setup_manager.py`
- Modify: `tests/test_usable_studio.py`

**Interfaces:**

- Consumes: `AccelerationManager`, `MODEL_PLANS`, `FullStudioStore`, current `SerialJobRunner`.
- Produces: fixed status/plans/recheck/install/selection APIs and durable job progress.

- [ ] **Step 1: Write failing safe-input and lifecycle tests**

```python
def test_acceleration_plans_are_fixed_public_metadata(client: TestClient) -> None:
    response = client.get("/api/acceleration/plans")

    assert response.status_code == 200
    assert {item["id"] for item in response.json()} >= {"onnxruntime_cuda_128", "yunet_2023mar"}
    assert all("command" not in item for item in response.json())


def test_browser_cannot_submit_url_or_package(client: TestClient) -> None:
    response = client.post("/api/acceleration/install", json={"plan_id": "pip install evil", "url": "https://evil.test"})

    assert response.status_code == 422


def test_research_install_requires_saved_acknowledgement(client: TestClient) -> None:
    response = client.post("/api/acceleration/install", json={
        "plan_id": "insightface_buffalo_m_retinaface",
        "acknowledge_research_license": False,
    })

    assert response.status_code == 409
```

- [ ] **Step 2: Run test to verify failure**

Run: `python -m pytest tests/test_acceleration_api.py tests/test_setup_manager.py tests/test_usable_studio.py -q`  
Expected: FAIL because routes/status do not exist.

- [ ] **Step 3: Replace generic GPU badges with component evidence**

Extend `ComponentStatus` with optional `provider`, `model_id`, `probe_detail`, `error_code`. Existing fields remain valid. Setup status reports separate Whisper/PyTorch, ONNX Runtime CUDA, MediaPipe CPU/GPU, YuNet CPU/CUDA, and FFmpeg encoder states.

Replace stale `cu130` logic. Preserve current working `2.11.0+cu128` PyTorch; do not reinstall it. Add fixed plan:

```python
InstallPlan(
    component="onnxruntime_cuda_128",
    label="NVIDIA face tracking runtime (CUDA 12.8)",
    command=[python_executable, "-m", "pip", "install", "--upgrade", "onnxruntime-gpu[cuda,cudnn]==1.26.0"],
    requires_restart=False,
    detail="Installs CUDA 12.8 ONNX Runtime. AutoClip requires a successful YuNet CUDA inference.",
)
```

No CUDA Toolkit install requirement: ORT calls `preload_dlls()` to use matching PyTorch CUDA/cuDNN runtime libraries.

- [ ] **Step 4: Implement fixed API contracts and serial jobs**

```python
class AccelerationInstallRequest(BaseModel):
    plan_id: Literal[
        "onnxruntime_cuda_128", "yunet_2023mar",
        "insightface_buffalo_m_retinaface", "insightface_antelopev2_scrfd",
    ]
    acknowledge_research_license: bool = False


class AccelerationSelectionRequest(BaseModel):
    tracker_engine: TrackerEngine | None = None
    encoder_mode: EncoderMode | None = None
```

Register:

| Method | Route | Result |
|---|---|---|
| GET | `/api/acceleration/status` | Full verified `AccelerationStatus` |
| GET | `/api/acceleration/plans` | Fixed plan metadata without command |
| POST | `/api/acceleration/recheck` | Fresh verified status |
| POST | `/api/acceleration/install` | `202 {"job_id": "..."}` |
| PATCH | `/api/projects/{project_id}/acceleration` | Saved `ProjectAcceleration` |

Create a `setup:acceleration:<plan_id>` job using existing serial runner. Persist research acknowledgement before downloader starts. Return 409 for `requires_acknowledgement`, `nvenc_error`, or `no_tracker_engine`; 422 invalid body; 404 project absent. Project detail adds `acceleration` and per-clip `tracking_resolution`. Runtime health gains additive `acceleration` while legacy properties remain.

- [ ] **Step 5: Run and commit**

```powershell
python -m pytest tests/test_acceleration_api.py tests/test_setup_manager.py tests/test_usable_studio.py tests/test_cli_web.py -q
git add autoclip/web/setup_manager.py autoclip/web/studio_server.py autoclip/web/usable_studio.py tests/test_acceleration_api.py tests/test_setup_manager.py tests/test_usable_studio.py
git commit -m "feat: expose safe GPU acceleration controls"
```

Expected tests: PASS. Run Git commands only if repository exists.

### Task 7: Indonesian/English Setup Center and studio controls

**Files:**

- Create: `web/ux/AccelerationCenter.tsx`
- Create: `web/ux/AccelerationCenter.test.tsx`
- Modify: `web/ux/SetupStudio.tsx`
- Modify: `web/src/api.ts`
- Modify: `web/src/App.tsx`
- Create: `web/src/AccelerationControls.test.tsx`
- Modify: `web/ux/setup.css`

**Interfaces:**

- Consumes: Task 6 routes and existing job WebSocket.
- Produces: accessible bilingual recommendation, status, install, acknowledgement, retry, project override, and metadata UI.

- [ ] **Step 1: Write failing component tests**

```tsx
it("shows YuNet CUDA recommendation and saves CPU override", async () => {
  render(<AccelerationCenter client={readyWindowsClient} locale="id" projectId="project-1" />);

  expect(screen.getByText("Rekomendasi: YuNet CUDA")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Gunakan CPU MediaPipe" }));
  expect(readyWindowsClient.setProjectAcceleration).toHaveBeenCalledWith("project-1", {
    tracker_engine: "mediapipe_cpu",
  });
});


it("gates InsightFace download behind acknowledgement", async () => {
  render(<AccelerationCenter client={researchClient} locale="en" />);

  await userEvent.click(screen.getByRole("button", { name: "Install SCRFD" }));
  expect(screen.getByText("Model assets are for non-commercial research only.")).toBeVisible();
  expect(screen.getByRole("button", { name: "Download model" })).toBeDisabled();
});
```

- [ ] **Step 2: Run tests to verify failure**

Run from `web`: `npm run test -- --run web/ux/AccelerationCenter.test.tsx web/src/AccelerationControls.test.tsx`  
Expected: FAIL because types/client/component are absent.

- [ ] **Step 3: Add typed client and accessible reusable controls**

Add matching `TrackerEngine`, `EncoderMode`, `RuntimeState`, `EngineCapability`, `EncoderCapability`, `AccelerationStatus`, `AccelerationPlan`, `ProjectAcceleration`, and methods `getAccelerationStatus`, `listAccelerationPlans`, `recheckAcceleration`, `installAcceleration`, `setProjectAcceleration` to `web/src/api.ts`.

Render Auto first with exact provider/model/encoder or exact reason. Each manual choice shows CPU/GPU, source/license/size, state, recheck/retry action. Show Radix research dialog; download button activates only after checkbox. Never offer arbitrary URL/command input.

Use this Indonesian copy:

```ts
auto: "Otomatis",
recommended: "Rekomendasi",
researchOnly: "Aset model hanya untuk riset non-komersial.",
acknowledge: "Saya memahami batas lisensi model ini.",
verified: "Terverifikasi dengan inferensi nyata",
notVerified: "Belum terverifikasi",
```

Use equivalent English:

```ts
auto: "Auto",
recommended: "Recommended",
researchOnly: "Model assets are for non-commercial research only.",
acknowledge: "I understand this model's license restriction.",
verified: "Verified by live inference",
notVerified: "Not verified",
```

- [ ] **Step 4: Mount in setup and editor**

Replace single Setup Center “GPU Whisper” badge with `AccelerationCenter` under hardware. Show Whisper, ONNX Runtime, MediaPipe GPU, YuNet, and FFmpeg encoder separately.

Add compact project controls above subject selector in `App.tsx` inspector. Selection calls `setProjectAcceleration`, refreshes project detail, marks current preview stale, and disables export until new preview approval. Preserve locked subject. Export history labels `artifact.metadata.encoder` and `artifact.metadata.tracker_engine`.

Use existing charcoal/orange visual system, keyboard focus, 44px actions, no gradients/new shadow language.

- [ ] **Step 5: Run frontend verification and commit**

```powershell
Set-Location web
npm run test -- --run web/ux/AccelerationCenter.test.tsx web/src/AccelerationControls.test.tsx web/ux/SetupStudio.test.tsx web/src/App.test.tsx
npm run check
npm run build
npx vite build --config studio.vite.config.ts
npx vite build --config setup.vite.config.ts
git add web/src/api.ts web/src/App.tsx web/ux/AccelerationCenter.tsx web/ux/SetupStudio.tsx web/ux/setup.css web/ux/AccelerationCenter.test.tsx web/src/AccelerationControls.test.tsx
git commit -m "feat: add GPU acceleration controls"
```

Expected: all build/test commands PASS. Fix existing TypeScript test globals/config errors and remove obsolete `web/src/App.ts` facade if `App.tsx` is canonical. Run Git commands only if repository exists.

### Task 8: CLI behavior, documentation, and full verification

**Files:**

- Modify: `autoclip/core/clipper.py`
- Modify: `autoclip/core/tracker.py`
- Modify: `autoclip/cli/__init__.py`
- Modify: `README.md`
- Modify: `SETUP_CENTER.md`
- Modify: `CONTRIBUTING.md`
- Test: `tests/test_tracker.py`
- Test: `tests/test_clipper.py`
- Test: `tests/test_cli_web.py`
- Create: `tests/test_gpu_smoke.py`

**Interfaces:**

- Consumes: compatible `TrackerConfig.engine`/`OutputConfig.encoder_mode` and shared resolver.
- Produces: CLI no-silent-GPU-fallback policy, local setup docs, automated/manual hardware evidence.

- [ ] **Step 1: Write failing CLI and hardware smoke tests**

```python
def test_cli_explicit_gpu_tracking_never_static_crops_when_missing(...) -> None:
    config = AutoClipConfig.model_validate({"tracker": {"enabled": True, "engine": "yunet_cuda"}})

    with pytest.raises(TrackerUnavailable, match="yunet_cuda"):
        create_clips(..., config=config)


@pytest.mark.gpu
def test_windows_yunet_cuda_live_smoke() -> None:
    capability = AccelerationManager().status().engine("yunet_cuda")

    assert capability.state == "ready"
    assert capability.provider == "CUDAExecutionProvider"


@pytest.mark.gpu
def test_nvenc_live_smoke() -> None:
    assert AccelerationManager().status().encoder("h264_nvenc").state == "ready"
```

- [ ] **Step 2: Run tests to verify current fallback conflict**

Run: `python -m pytest tests/test_tracker.py tests/test_clipper.py tests/test_cli_web.py tests/test_gpu_smoke.py -q`  
Expected: explicit GPU test FAILS until old broad static-crop fallback is removed.

- [ ] **Step 3: Share resolver with CLI without implicit downloads**

Route clipper through `AccelerationSelection(config.tracker.engine, config.output.encoder_mode)` and `VideoEncoding`. For explicit engine, raise `TrackerUnavailable` with engine/state and repair guidance `autoclip web`. For auto, CPU MediaPipe/YuNet is valid. When `tracker.enabled is False`, retain intentional non-tracking centre crop. CLI never downloads packages/models.

- [ ] **Step 4: Add exact docs and run full verification**

Document Windows RTX 5070 path: existing PyTorch CUDA works; Setup Center installs `onnxruntime-gpu[cuda,cudnn]==1.26.0` then YuNet; live inference/recheck is required; Auto then selects YuNet CUDA. State that FFmpeg needs successful `h264_nvenc` smoke, Windows GPU tracking uses YuNet CUDA, MediaPipe GPU is Ubuntu-only, no CUDA Toolkit install is needed when PyTorch provides matching libraries, YuNet is MIT, InsightFace assets are research-only, and all face work stays local without embeddings.

Document commands:

```powershell
autoclip web
python -c "import torch; print(torch.__version__); print(torch.version.cuda); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0))"
ffmpeg -hide_banner -encoders | Select-String nvenc
```

Run:

```powershell
python -m pytest -q
Set-Location web
npm run check
npm run test
npm run build
npx vite build --config studio.vite.config.ts
npx vite build --config setup.vite.config.ts
```

Expected: all PASS. Do not claim release readiness with any Python, TypeScript, Vitest, or build failure.

- [ ] **Step 5: Manual hardware matrix and commit**

Record outcomes in `SETUP_CENTER.md`:

| Machine | Required evidence |
|---|---|
| Windows RTX 5070 | `yunet_cuda` ready with `CUDAExecutionProvider`; subject-lock preview; approved `h264_nvenc` MP4; artifact metadata names both. |
| Ubuntu NVIDIA | `mediapipe_gpu` ready only after live VIDEO inference; repeat lock/gap/preview/export. |
| CPU-only | GPU states explain unavailable; Auto uses CPU tracker and `libx264`; no false GPU badge. |

For preview/export, compare trajectory `centers` and selected face track: both must match. Force face-loss fixture and confirm persisted gap plus hold/ease behaviour.

```powershell
git add autoclip/core/clipper.py autoclip/core/tracker.py autoclip/cli/__init__.py README.md SETUP_CENTER.md CONTRIBUTING.md tests/test_tracker.py tests/test_clipper.py tests/test_cli_web.py tests/test_gpu_smoke.py
git commit -m "test: verify GPU acceleration workflow"
```

Run Git commands only if repository exists.

## Plan Self-Review

- Coverage: Tasks 1–3 define identifiers, resolver ordering, compatibility, strict live GPU detection, commercial-safe YuNet, Ubuntu MediaPipe GPU, and optional InsightFace detectors. Tasks 2/6 enforce checksums, acknowledgement, allow-listed inputs, fixed installers, serial jobs, and exact status. Tasks 4/5 persist selected/resolved runtime, trajectory, encoder metadata, and strict NVENC export. Task 7 provides bilingual selection/install/error UI. Task 8 retains CLI behavior and proves Windows, Ubuntu, and CPU-only results.
- Placeholder scan: pinned model sources/hashes/sizes, package version, APIs, error codes, status rules, test commands, data records, and user copy are all explicit.
- Type consistency: Task 1 owns all identifiers. `ResolvedAcceleration` flows to detector, store, renderer, API, and UI. `VideoEncoding` flows from FFmpeg resolver to crop/render metadata.
