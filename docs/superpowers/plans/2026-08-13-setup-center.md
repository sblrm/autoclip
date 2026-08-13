# Setup Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a local guided setup and onboarding experience that can repair dependencies and configure NVIDIA GPU acceleration without misleading users.

**Architecture:** Add a small testable setup domain that probes and runs only allow-listed local commands. Wrap the existing FastAPI editor server with setup endpoints and a new Vite entrypoint, preserving current editing APIs and project state.

**Tech Stack:** Python 3.10+, FastAPI, subprocess, Windows Package Manager, pip, React 19, Vite, TypeScript, Vitest.

## Global Constraints

- All installs begin only after browser user action.
- FFmpeg uses Windows Package Manager; Python tools use the active interpreter's pip.
- NVIDIA GPU upgrade uses official PyTorch CUDA 13.0 wheels matching installed torch major/minor version.
- Status reports acceleration per component, never as one global application mode.
- Existing project, clip, preview, approval, and export APIs remain intact.

---

### Task 1: Testable setup domain

**Files:**
- Create: `tests/test_setup_manager.py`
- Create: `autoclip/web/setup_manager.py`

**Interfaces:**
- Produces `SetupManager.status() -> SetupStatus` and `SetupManager.install_plan(component: str) -> InstallPlan`.
- `SetupStatus` serializes to JSON with `components`, `hardware`, `is_ready`, and `tutorial_steps`.

- [ ] **Step 1: Write failing tests**

```python
def test_status_exposes_cpu_only_whisper_and_detected_nvidia_adapter() -> None:
    manager = SetupManager(probe=FakeProbe(nvidia_name="RTX 5070", torch_cuda=False))
    status = manager.status()
    assert status.hardware.adapter == "RTX 5070"
    assert status.components["whisper"].acceleration == "cpu"

def test_gpu_plan_reinstalls_matching_torch_version_from_official_cuda_index() -> None:
    manager = SetupManager(probe=FakeProbe(nvidia_name="RTX 5070", torch_version="2.12.0+cpu"))
    plan = manager.install_plan("whisper_gpu")
    assert plan.command[-2:] == ["--index-url", "https://download.pytorch.org/whl/cu130"]
    assert "torch==2.12.0" in plan.command
```

- [ ] **Step 2: Run focused tests; expected failure**

Run: `.venv\\Scripts\\python.exe -m pytest tests/test_setup_manager.py -v`

Expected: `ModuleNotFoundError: No module named 'autoclip.web.setup_manager'`.

- [ ] **Step 3: Implement smallest setup manager**

```python
class SetupManager:
    def status(self) -> SetupStatus: ...
    def install_plan(self, component: str) -> InstallPlan: ...
    def install(self, component: str, report: Reporter) -> None: ...
```

Use `subprocess.run(command, shell=False, capture_output=True, text=True)`. Reject unknown components with `ValueError`.

- [ ] **Step 4: Run focused tests; expected pass**

Run: `.venv\\Scripts\\python.exe -m pytest tests/test_setup_manager.py -v`

Expected: PASS.

### Task 2: Setup API and serial installation jobs

**Files:**
- Create: `tests/test_usable_studio.py`
- Create: `autoclip/web/usable_studio.py`

**Interfaces:**
- Consumes `SetupManager` and existing `create_studio_server`.
- Produces `GET /api/setup/status`, `POST /api/setup/recheck`, and `POST /api/setup/install`.

- [ ] **Step 1: Write failing API tests**

```python
def test_setup_status_and_install_job_are_available(tmp_path: Path) -> None:
    app = create_usable_studio(tmp_path / "projects", setup_manager=FakeManager())
    client = TestClient(app)
    assert client.get("/api/setup/status").json()["is_ready"] is True
    assert client.post("/api/setup/install", json={"component": "opencv"}).status_code == 202
```

- [ ] **Step 2: Run test; expected failure**

Run: `.venv\\Scripts\\python.exe -m pytest tests/test_usable_studio.py -v`

Expected: import failure for `create_usable_studio`.

- [ ] **Step 3: Add wrapper endpoints**

Use existing `SerialJobRunner` to run installer and send its progress through existing job WebSocket. Expose no arbitrary command endpoint.

- [ ] **Step 4: Run focused tests; expected pass**

Run: `.venv\\Scripts\\python.exe -m pytest tests/test_usable_studio.py -v`

Expected: PASS.

### Task 3: Guided React entrypoint

**Files:**
- Create: `web/ux.html`
- Create: `web/ux/main.tsx`
- Create: `web/ux/SetupStudio.tsx`
- Create: `web/ux/setup.css`
- Create: `web/ux/SetupStudio.test.tsx`
- Create: `web/setup.vite.config.ts`

**Interfaces:**
- Consumes setup status and install job endpoints.
- Produces welcome/tutorial, Setup Center, per-component installer cards, and editor-entry CTA.

- [ ] **Step 1: Write failing UI tests**

```tsx
test("first launch teaches the five-step workflow before import", async () => {
  render(<SetupStudio client={readyClient} />);
  expect(await screen.findByText("Ready to make your first cut?")).toBeVisible();
  expect(screen.getByText("1. Set up engine")).toBeVisible();
});

test("GPU label belongs to Whisper, not face tracking", async () => {
  render(<SetupStudio client={gpuCandidateClient} />);
  expect(await screen.findByText("Whisper transcription · CPU")).toBeVisible();
  expect(screen.getByText("Face tracking · CPU")).toBeVisible();
});
```

- [ ] **Step 2: Run UI test; expected failure**

Run: `npm --prefix web run test -- --config setup.vite.config.ts`

Expected: entrypoint import failure.

- [ ] **Step 3: Implement responsive Setup Center**

Use Indonesian default and English switch. Include first-run tutorial, component cards, visible install command disclosure, real install progress, retry state, and an explicit `Enter studio` button when required components are ready.

- [ ] **Step 4: Run UI test; expected pass**

Run: `npm --prefix web run test -- --config setup.vite.config.ts`

Expected: PASS.

### Task 4: Usable launcher, docs, and full verification

**Files:**
- Create: `autoclip-setup-studio.bat`
- Create: `SETUP_CENTER.md`

- [ ] **Step 1: Build dedicated entrypoint**

Run: `Push-Location web; .\\node_modules\\.bin\\vite.cmd build --config .\\setup.vite.config.ts; Pop-Location`

Expected: `web/dist/ux.html` and hashed assets exist.

- [ ] **Step 2: Browser smoke test**

Run launch script, open `http://127.0.0.1:8765`, verify tutorial, setup cards, and editor entry.

- [ ] **Step 3: Run regression suites**

Run: `.venv\\Scripts\\python.exe -m pytest -q; npm --prefix web run check; npm --prefix web run test`

Expected: all relevant tests pass.
