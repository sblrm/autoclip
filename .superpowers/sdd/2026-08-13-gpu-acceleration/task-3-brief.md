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

Refactor `MediaPipeTasksDetector` to accept optional `mp.tasks.BaseOptions.Delegate` and pass it to `BaseOptions(model_asset_path=..., delegate=delegate)`. Keep `RunningMode.VIDEO` and `detect_for_video`. Offer GPU only when `platform.freedesktop_os_release()["ID"] == "ubuntu"`; create detector and infer one generated 320×320 BGR frame before ready.

Implement `YuNetOnnxDetector` with 320×320 letterboxed BGR-to-RGB float32 NCHW input, scale/padding reversal, YuNet box/score decode, IoU 0.3 NMS, normalized/clamped `FaceObservation`. Order output confidence descending then x/y ascending. Construct ORT:

```python
onnxruntime.preload_dlls()
session = onnxruntime.InferenceSession(
    str(model_path),
    providers=["CUDAExecutionProvider"] if cuda else ["CPUExecutionProvider"],
)
if expected_provider not in session.get_providers():
    raise TrackerUnavailable(f"{engine} did not create {expected_provider}")
```

Never supply CPU fallback provider for `*_cuda`. Implement `InsightFaceOnnxDetector` only for extraction-only detector ONNX files; it may use detector preprocessing/anchor utilities but never recognition models/persisted embeddings.

- [ ] **Step 4: Implement full live capability states and pass tests**

`AccelerationManager` checks OS/distro, NVIDIA name/driver, PyTorch CUDA, `onnxruntime.get_available_providers()`, `preload_dlls()`, actual YuNet session/inference, MediaPipe CPU/GPU detection inference, and model cache/hash. Tests prove model absent is `missing`; non-Ubuntu MediaPipe GPU is `unsupported`; CUDA session exception is `failed` with scrubbed detail; empty face result proves inference not fallback; explicit GPU cannot call CPU detector.

Run:

```powershell
.\\.venv\\Scripts\\python.exe -m pytest tests/test_detectors.py tests/test_acceleration_manager.py tests/test_web_tracking.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit when repository exists**

```powershell
git add autoclip/web/detectors.py autoclip/web/acceleration_manager.py autoclip/web/tracking.py tests/test_detectors.py tests/test_acceleration_manager.py
git commit -m "feat: add verified face detector engines"
```

No Git root. Do not initialize/reset one.
