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

Run: `.\\.venv\\Scripts\\python.exe -m pytest tests/test_nvenc.py tests/test_tracking_render_integration.py -q`  
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

Parse `ffmpeg -hide_banner -encoders` before smoke. Exact arguments:

- `libx264`: `["-c:v", "libx264", "-crf", "23", "-preset", "medium"]`;
- `h264_nvenc`: `["-c:v", "h264_nvenc", "-preset", "p5", "-cq", "23", "-b:v", "0"]`;
- `hevc_nvenc`: `["-c:v", "hevc_nvenc", "-preset", "p5", "-cq", "25", "-b:v", "0"]`.

`apply_face_crop` accepts `encoding: VideoEncoding` and appends exact arguments. Remove unconditional `libx264`, preserve AAC.

- [ ] **Step 4: Save detector identity once and reuse trajectory**

At `detect_tracks`, load project selection, resolve status, create one detector, save `ClipTrackingResolution`. Trajectory JSON includes tracker engine/provider/model. Preview/export load saved resolution, resolve encoder, crop using `encoding`, save:

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

Preview/export can differ dimensions but never rerun detection/change track/change detector. Missing resolution becomes job error, never centre crop.

- [ ] **Step 5: Run**

```powershell
.\\.venv\\Scripts\\python.exe -m pytest tests/test_nvenc.py tests/test_tracking_render_integration.py tests/test_tracking_service.py tests/test_web_tracking.py -q
```

Expected: PASS. No Git root.
