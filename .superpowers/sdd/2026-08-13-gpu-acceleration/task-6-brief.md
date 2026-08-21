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

Run: `.\\.venv\\Scripts\\python.exe -m pytest tests/test_acceleration_api.py tests/test_setup_manager.py tests/test_usable_studio.py -q`  
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

Create `setup:acceleration:<plan_id>` job using current serial runner. Persist research acknowledgement before downloader starts. Return 409 for `requires_acknowledgement`, `nvenc_error`, or `no_tracker_engine`; 422 invalid body; 404 project absent. Project detail adds `acceleration` and per-clip `tracking_resolution`. Runtime health gains additive `acceleration` while legacy properties remain.

- [ ] **Step 5: Run**

```powershell
.\\.venv\\Scripts\\python.exe -m pytest tests/test_acceleration_api.py tests/test_setup_manager.py tests/test_usable_studio.py tests/test_cli_web.py -q
```

Expected: PASS. No Git root.
