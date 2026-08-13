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

Current workspace has no Git root. Do not initialize/reset one only to record this step.
