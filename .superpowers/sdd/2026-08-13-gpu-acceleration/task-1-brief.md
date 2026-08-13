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
