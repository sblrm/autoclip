# Usable Local Studio Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `autoclip web` a durable local Home + Studio experience with guided setup, clear CPU/GPU profiles, safe in-app repair, and release-ready launch behavior.

**Architecture:** Add a server-owned onboarding layer above existing SetupManager, AccelerationManager, and FullStudioStore. Serve one routed React app from FastAPI; Home consumes onboarding state while existing project editor keeps its durable clip/tracking contracts. Move browser launching and asset discovery into a testable Python launcher, with Vite used only to create package assets during build/release.

**Tech Stack:** Python 3.10+, FastAPI, SQLite, existing SerialJobRunner, React 19, TypeScript, Tailwind v4, Vite, Vitest, pytest.

**Spec:** `docs/superpowers/specs/2026-08-21-usable-local-studio-design.md`

## Global Constraints

- Keep all processing and storage local. Do not add accounts, telemetry, remote processing, face recognition, or arbitrary browser-supplied commands.
- Keep setup/install work serialized through `SerialJobRunner`; every install remains a fixed server-side allow-list plan.
- Indonesian is default UI language; English remains a switchable alternative.
- `Auto` may choose verified CPU after a GPU probe fails. Explicit `GPU` must fail with recovery instructions, never silently use CPU or center crop.
- GPU tracker evidence requires live inference. NVENC evidence requires a real smoke encode.
- YuNet remains standard; SCRFD/RetinaFace remain opt-in research-only downloads with acknowledgement.
- Preserve saved subject locks, gaps, preview trajectories, approval gate, and CLI commands.
- Normal `autoclip web` runtime must not invoke Vite, require Node, or rebuild web assets.

---

## File Structure

- Create: `autoclip/web/onboarding.py` — preference, readiness, profile-resolution, and repair-batch contracts.
- Create: `autoclip/web/launch.py` — health-waiting localhost launcher and default-browser integration.
- Create: `tests/test_onboarding.py` — store/service/profile/batch unit tests.
- Create: `tests/test_web_launch.py` — no-browser launch orchestration tests.
- Create: `web/src/routes.ts` — History API route parser/navigator for Home, project, and Settings.
- Create: `web/src/OnboardingHome.tsx` — Home readiness, project resume, setup repair, and tutorial UI.
- Create: `web/src/PerformanceSettings.tsx` — profile chooser, repair detail, logs, and advanced engine controls.
- Create: `web/src/OnboardingHome.test.tsx` — Home flow, locale, refresh-safe routing, repair UI tests.
- Create: `web/src/PerformanceSettings.test.tsx` — profile, acknowledgement, retry, and GPU failure UI tests.
- Modify: `autoclip/web/runtime_store.py` — `app_preferences` schema and typed persistence methods.
- Modify: `autoclip/web/setup_manager.py` — platform-aware fixed FFmpeg plan and batch-safe plan metadata.
- Modify: `autoclip/web/studio_server.py` — onboarding, preference, repair, structured-error, and profile-aware import APIs.
- Modify: `autoclip/web/usable_studio.py` — serve one package/static app entry rather than `ux.html`.
- Modify: `autoclip/cli/__init__.py` — delegate `autoclip web` to `launch.run_web`.
- Modify: `pyproject.toml` — include built static assets in package artifacts.
- Modify: `web/vite.config.ts`, `web/index.html`, `web/src/main.tsx` — one production entry and package static output.
- Modify: `web/src/api.ts` — onboarding/preference/error types and client methods.
- Modify: `web/src/App.tsx` — routed app shell; keep editor behavior inside project route.
- Modify: `web/ux/AccelerationCenter.tsx` — advanced-only engine/encoder controls reusable from Settings.
- Modify: `web/src/styles.css` and `web/ux/setup.css` — consolidated Home/Settings styling.
- Modify: `README.md`, `SETUP_CENTER.md`, `CONTRIBUTING.md` — release/source launch and repair documentation.
- Modify: `autoclip-setup-studio.bat`, `autoclip-web-studio.bat`, `launch-autoclip-web-studio.bat`, `start-autoclip-web-studio.bat` — compatibility wrappers only.
- Delete after migration: `web/ux/main.tsx`, `web/ux/SetupStudio.tsx`, `web/ux/SetupStudio.ts`, `web/ux/SetupStudioImpl.ts`, `web/ux/SetupStudioImpl.tsx`, `web/ux/SetupStudioImpl.js`, `web/ux/SetupStudio.test.tsx`.

## Task 1: Persist Application Preferences and Profile Contracts

**Files:**
- Modify: `autoclip/web/runtime_store.py`
- Create: `tests/test_onboarding.py`
- Test: `tests/test_full_store.py`

**Interfaces:**
- Produces `PerformanceProfile = Literal["auto", "cpu", "gpu"]` and `AppPreferences(locale, last_project_id, onboarding_complete, performance_profile, updated_at)`.
- Produces `RuntimeStore.get_app_preferences() -> AppPreferences` and `RuntimeStore.update_app_preferences(**changes) -> AppPreferences`.
- Existing `ProjectAcceleration` remains per-project and is not changed by this task.

- [ ] **Step 1: Write failing SQLite persistence tests**

```python
def test_app_preferences_default_and_partial_update(tmp_path: Path) -> None:
    store = RuntimeStore(tmp_path / "library")

    assert store.get_app_preferences().performance_profile == "auto"
    saved = store.update_app_preferences(locale="en", last_project_id="p1", performance_profile="cpu")

    assert saved.locale == "en"
    assert saved.last_project_id == "p1"
    assert RuntimeStore(tmp_path / "library").get_app_preferences() == saved


def test_app_preferences_reject_invalid_profile(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="performance_profile"):
        RuntimeStore(tmp_path / "library").update_app_preferences(performance_profile="cuda")
```

- [ ] **Step 2: Run preference tests and verify failure**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_onboarding.py -q`

Expected: FAIL because `get_app_preferences` does not exist.

- [ ] **Step 3: Add schema, dataclass, and validated accessors**

```python
PerformanceProfile = Literal["auto", "cpu", "gpu"]

@dataclass(frozen=True)
class AppPreferences:
    locale: str = "id"
    last_project_id: str | None = None
    onboarding_complete: bool = False
    performance_profile: PerformanceProfile = "auto"
    updated_at: str = ""

def update_app_preferences(self, **changes: object) -> AppPreferences:
    allowed = {"locale", "last_project_id", "onboarding_complete", "performance_profile"}
    unknown = set(changes) - allowed
    if unknown:
        raise ValueError(f"unknown preference fields: {sorted(unknown)}")
    current = self.get_app_preferences()
    values = {field: changes.get(field, getattr(current, field)) for field in allowed}
    if values["locale"] not in {"id", "en"} or values["performance_profile"] not in {"auto", "cpu", "gpu"}:
        raise ValueError("invalid app preference")
    self._upsert_app_preferences(**values, updated_at=_utc_now())
    return self.get_app_preferences()
```

Create `app_preferences` in `RuntimeStore._initialize()` with singleton primary key and JSON-free scalar columns. Use `_utc_now()` for every write. Keep migrations additive with `CREATE TABLE IF NOT EXISTS`.

- [ ] **Step 4: Run focused storage tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_onboarding.py tests/test_full_store.py -q`

Expected: PASS.

- [ ] **Step 5: Commit preference contract**

```bash
git add autoclip/web/runtime_store.py tests/test_onboarding.py
git commit -m "feat: persist studio preferences"
```

## Task 2: Add Readiness, Profile Resolution, and Repair-Batch Services

**Files:**
- Create: `autoclip/web/onboarding.py`
- Modify: `autoclip/web/setup_manager.py`
- Modify: `tests/test_setup_manager.py`
- Modify: `tests/test_onboarding.py`

**Interfaces:**
- Consumes `RuntimeStore`, `SetupManager.status()`, `SetupManager.install_plan()`, `SetupManager.install()`, and `AccelerationStatus.resolve()`.
- Produces `OnboardingService.snapshot() -> OnboardingSnapshot`, `set_profile(profile) -> ProfileResolution`, `apply_profile(project_id) -> ProjectAcceleration`, `repair_required(report) -> None`.
- Produces `ProfileUnavailable(code, title, recovery_action, retryable)` for explicit GPU preflight failure.

- [ ] **Step 1: Write failing service tests for profiles and repair order**

```python
def test_gpu_profile_requires_verified_tracker_and_nvenc() -> None:
    service = make_service(
        engines={"yunet_cuda": ("ready", "CUDAExecutionProvider", "yunet_2023mar")},
        encoders={"libx264": "ready"},
    )

    with pytest.raises(ProfileUnavailable, match="gpu_encoder_unavailable"):
        service.set_profile("gpu")


def test_repair_required_skips_ready_components_and_rechecks_each_child() -> None:
    setup = FakeSetupManager(required=("ffmpeg", "opencv", "whisper"), ready={"ffmpeg"})
    service = make_service(setup=setup)
    events: list[tuple[str, float, str]] = []

    service.repair_required(lambda stage, progress, message: events.append((stage, progress, message)))

    assert setup.installed == ["opencv", "whisper"]
    assert events[-1][0] == "repair_ready"
```

- [ ] **Step 2: Run service tests and verify failure**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_onboarding.py tests/test_setup_manager.py -q`

Expected: FAIL because `autoclip.web.onboarding` is absent.

- [ ] **Step 3: Implement minimal service and platform-safe setup plans**

```python
class OnboardingService:
    def snapshot(self) -> OnboardingSnapshot:
        return self._compose_snapshot(self.setup_manager.status(), self.acceleration_manager.status())

    def set_profile(self, profile: PerformanceProfile) -> ProfileResolution:
        resolution = self._resolve_profile(profile, self.acceleration_manager.status())
        self.store.update_app_preferences(performance_profile=profile)
        return resolution

    def apply_profile(self, project_id: str) -> ProjectAcceleration:
        selection = self._resolve_profile(self.store.get_app_preferences().performance_profile, self.acceleration_manager.status())
        return self.store.set_project_acceleration(project_id, tracker_engine=selection.tracker_engine, encoder_mode=selection.encoder_mode)

    def repair_required(self, report: Reporter) -> None:
        for component in self._required_missing_component_ids():
            self.setup_manager.install(component, report)

def _selection_for_profile(profile: PerformanceProfile, status: AccelerationStatus) -> AccelerationSelection:
    if profile == "auto":
        return AccelerationSelection()
    if profile == "cpu":
        return AccelerationSelection(tracker_engine=_first_ready_cpu(status), encoder_mode="libx264")
    return AccelerationSelection(tracker_engine=_first_ready_gpu(status), encoder_mode="h264_nvenc")
```

Give `SetupManager` an injected `platform_name` defaulting to `platform.system()`. Keep Windows FFmpeg on fixed WinGet arguments. On Ubuntu return only `("pkexec", "apt-get", "install", "-y", "ffmpeg")`; reject other system-package platforms with `unsupported_platform`. Do not add shell strings, password fields, or browser-controlled command arguments.

`repair_required()` must derive components from latest required `SetupStatus`, exclude optional Ollama/research models/GPU upgrades, call `install_plan()` before running any child, report `repair:<component>` progress, and recheck after each child. A zero-work plan reports `repair_ready` without executing a command.

- [ ] **Step 4: Run service/setup regression tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_onboarding.py tests/test_setup_manager.py tests/test_acceleration_manager.py -q`

Expected: PASS.

- [ ] **Step 5: Commit onboarding service**

```bash
git add autoclip/web/onboarding.py autoclip/web/setup_manager.py tests/test_onboarding.py tests/test_setup_manager.py
git commit -m "feat: add guided setup readiness"
```

## Task 3: Expose Durable Onboarding and Structured Repair APIs

**Files:**
- Modify: `autoclip/web/studio_server.py`
- Modify: `autoclip/web/usable_studio.py`
- Modify: `tests/test_acceleration_api.py`
- Modify: `tests/test_usable_studio.py`
- Create: `tests/test_onboarding_api.py`

**Interfaces:**
- Consumes `OnboardingService` from Task 2 and existing `SerialJobRunner`/`Job` persistence.
- Produces `GET /api/onboarding`, `PATCH /api/preferences`, `POST /api/onboarding/repair`, and `POST /api/projects/{project_id}/apply-performance-profile`.
- Produces JSON errors `{ "code", "title", "recovery_action", "retryable", "component_id?", "job_id?" }` for onboarding/profile failures.

- [ ] **Step 1: Write failing API tests**

```python
def test_onboarding_payload_and_profile_preference_are_durable(client: TestClient) -> None:
    initial = client.get("/api/onboarding").json()
    changed = client.patch("/api/preferences", json={"locale": "en", "performance_profile": "cpu"})

    assert initial["recommended_action"]["id"] == "repair_required"
    assert changed.status_code == 200
    assert client.get("/api/onboarding").json()["preferences"]["performance_profile"] == "cpu"


def test_repair_endpoint_rejects_extra_browser_command_and_queues_one_job(client: TestClient) -> None:
    invalid = client.post("/api/onboarding/repair", json={"command": ["powershell"]})
    queued = client.post("/api/onboarding/repair", json={})

    assert invalid.status_code == 422
    assert queued.status_code == 202
    assert queued.json()["job_id"]
```

- [ ] **Step 2: Run onboarding API tests and verify failure**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_onboarding_api.py -q`

Expected: FAIL with 404 endpoints.

- [ ] **Step 3: Wire service into app state and endpoints**

```python
class PreferencesPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    locale: Literal["id", "en"] | None = None
    onboarding_complete: bool | None = None
    performance_profile: PerformanceProfile | None = None

@app.get("/api/onboarding")
def onboarding_status() -> dict[str, object]:
    return app.state.onboarding.snapshot().payload()

@app.post("/api/onboarding/repair", response_model=JobResponse, status_code=202)
def repair_required_setup() -> JobResponse:
    job = _create_setup_job(store, "repair_required")
    runner.submit(job, app.state.onboarding.repair_required)
    return JobResponse(job_id=job.id)
```

Create setup jobs with project ID `__setup__` through one shared helper, not duplicated direct SQL. On successful local/URL project creation, call `apply_profile(project.id)` only when stored preference is `cpu` or `gpu`; return structured profile error before claiming the project is configured. Keep explicit per-project acceleration PATCH and its invalidation semantics unchanged.

Install a FastAPI exception handler for `ProfileUnavailable` and setup-domain errors. Update existing frontend request parsing later to consume the structured payload while preserving plain FastAPI validation errors.

- [ ] **Step 4: Run API and existing studio tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_onboarding_api.py tests/test_usable_studio.py tests/test_acceleration_api.py tests/test_full_studio_api.py -q`

Expected: PASS.

- [ ] **Step 5: Commit onboarding APIs**

```bash
git add autoclip/web/studio_server.py autoclip/web/usable_studio.py tests/test_onboarding_api.py tests/test_usable_studio.py tests/test_acceleration_api.py
git commit -m "feat: expose guided setup APIs"
```

## Task 4: Make `autoclip web` a Release-Safe Launcher

**Files:**
- Create: `autoclip/web/launch.py`
- Modify: `autoclip/cli/__init__.py`
- Modify: `autoclip/web/usable_studio.py`
- Modify: `pyproject.toml`
- Modify: `web/vite.config.ts`
- Modify: `web/index.html`
- Modify: `autoclip-setup-studio.bat`
- Modify: `autoclip-web-studio.bat`
- Modify: `launch-autoclip-web-studio.bat`
- Modify: `start-autoclip-web-studio.bat`
- Create: `tests/test_web_launch.py`

**Interfaces:**
- Produces `run_web(host="127.0.0.1", preferred_port=8765, open_browser=webbrowser.open) -> int`.
- Produces `wait_for_health(url, timeout_seconds=15.0, request=urlopen) -> None`.
- Package static root is `autoclip/web/static`, served by `create_usable_studio()`.

- [ ] **Step 1: Write failing launcher tests without a real browser/server**

```python
def test_run_web_waits_for_health_then_opens_local_url() -> None:
    opened: list[str] = []
    result = run_web(
        server_factory=FakeServerFactory(started_after=2),
        health_waiter=lambda url, timeout_seconds: None,
        open_browser=opened.append,
    )

    assert result == 0
    assert opened == ["http://127.0.0.1:8765/"]


def test_missing_static_assets_has_recovery_message(tmp_path: Path) -> None:
    with pytest.raises(WebLaunchError, match="build frontend assets"):
        static_root_or_error(tmp_path / "missing")
```

- [ ] **Step 2: Run launcher tests and verify failure**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_web_launch.py -q`

Expected: FAIL because `autoclip.web.launch` is absent.

- [ ] **Step 3: Implement launch and single-build packaging**

```python
def run_web(*, host: str = "127.0.0.1", preferred_port: int = 8765,
            server_factory: ServerFactory = make_server,
            health_waiter: HealthWaiter = wait_for_health,
            open_browser: Callable[[str], bool] = webbrowser.open) -> int:
    port = find_available_local_port(host, preferred_port)
    url = f"http://{host}:{port}/"
    server = server_factory(host, port)
    thread = Thread(target=server.run, daemon=True)
    thread.start()
    health_waiter(f"{url}api/runtime-health", 15.0)
    open_browser(url)
    thread.join()
    return 0
```

Use a bounded localhost-only port probe. On startup/asset failure, stop server and raise a clear `WebLaunchError`; do not spawn a shell or invoke Vite.

Set Vite `build.outDir` to `../autoclip/web/static`, make `index.html` the only input, and configure Poetry `include` for `autoclip/web/static/**/*`. Update `create_usable_studio()` to serve package static `index.html`. Replace each batch file with a wrapper that calls the installed `autoclip` executable or active virtualenv `python -m autoclip.cli web`; no wrapper may call Vite.

- [ ] **Step 4: Run launcher/package and frontend build checks**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_web_launch.py -q`

Run (from `web/`): `npm.cmd run build`

Expected: both PASS; produced assets exist under `autoclip/web/static`.

- [ ] **Step 5: Commit release launcher**

```bash
git add autoclip/web/launch.py autoclip/cli/__init__.py autoclip/web/usable_studio.py pyproject.toml web/vite.config.ts web/index.html autoclip-setup-studio.bat autoclip-web-studio.bat launch-autoclip-web-studio.bat start-autoclip-web-studio.bat tests/test_web_launch.py
git commit -m "feat: launch packaged local studio"
```

## Task 5: Build Typed Client, Routes, and App Shell

**Files:**
- Create: `web/src/routes.ts`
- Modify: `web/src/api.ts`
- Modify: `web/src/App.tsx`
- Modify: `web/src/main.tsx`
- Modify: `web/src/StudioApp.test.tsx`
- Modify: `web/src/StudioSmoke.test.tsx`
- Modify: `web/src/StudioVerify.test.tsx`

**Interfaces:**
- Produces `Route = { kind: "home" } | { kind: "project"; projectId: string } | { kind: "settings" }`.
- Produces `readRoute(location)`, `navigate(route)`, and `useRoute()` backed by History API and `popstate`.
- Produces typed `OnboardingSnapshot`, `AppPreferences`, `RepairAction`, and `StudioClient.getOnboarding()/updatePreferences()/repairRequiredSetup()`.

- [ ] **Step 1: Write failing route/client tests**

```tsx
test("restores Home, Settings, and project routes after browser navigation", () => {
  expect(readRoute(new URL("http://local.test/"))).toEqual({ kind: "home" });
  expect(readRoute(new URL("http://local.test/projects/p-1"))).toEqual({ kind: "project", projectId: "p-1" });
  expect(readRoute(new URL("http://local.test/settings"))).toEqual({ kind: "settings" });
});
```

- [ ] **Step 2: Run route/client tests and verify failure**

Run (from `web/`): `npm.cmd run test -- src/StudioApp.test.tsx`

Expected: FAIL because `routes.ts` and onboarding client methods do not exist.

- [ ] **Step 3: Implement route-safe shell and typed API**

```ts
export interface StudioClient extends AccelerationClient {
  getOnboarding(): Promise<OnboardingSnapshot>;
  updatePreferences(patch: Partial<AppPreferences>): Promise<AppPreferences>;
  repairRequiredSetup(): Promise<JobCreated>;
}

export function useRoute(): [Route, (next: Route) => void] {
  const [route, setRoute] = useState(() => readRoute(window.location));
  useEffect(() => {
    const onPopState = () => setRoute(readRoute(window.location));
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);
  const navigate = (next: Route) => {
    window.history.pushState({}, "", pathForRoute(next));
    setRoute(next);
  };
  return [route, navigate];
}
```

Refactor `App` into route shell while preserving existing project editor callbacks, preview stale detection, approval gate, and `AccelerationCenter` integration. Home is default even when project list exists. Editor loads only for a `/projects/:id` route. Settings is reachable without selecting a project.

Update `request()` to prefer structured error `title` and append `recovery_action` when present; retain `detail` fallback for FastAPI validation.

- [ ] **Step 4: Run existing editor regression tests**

Run (from `web/`): `npm.cmd run test -- src/StudioApp.test.tsx src/StudioSmoke.test.tsx src/StudioVerify.test.tsx`

Expected: PASS with existing subject-selection and export-approval assertions intact.

- [ ] **Step 5: Commit typed route shell**

```bash
git add web/src/routes.ts web/src/api.ts web/src/App.tsx web/src/main.tsx web/src/StudioApp.test.tsx web/src/StudioSmoke.test.tsx web/src/StudioVerify.test.tsx
git commit -m "feat: add durable studio routes"
```

## Task 6: Implement Guided Home and Live Tutorial

**Files:**
- Create: `web/src/OnboardingHome.tsx`
- Create: `web/src/OnboardingHome.test.tsx`
- Modify: `web/src/App.tsx`
- Modify: `web/src/styles.css`

**Interfaces:**
- Consumes `OnboardingSnapshot`, `Project[]`, route navigation, and typed repair API from Task 5.
- Produces `OnboardingHome` props `{ client, locale, projects, snapshot, onOpenProject, onStartProject, onOpenSettings }`.
- Uses existing `StudioClient.watchJob()` for repair progress and automatic onboarding refresh on terminal job state.

- [ ] **Step 1: Write failing Home flow tests**

```tsx
test("Home shows one repair action, Indonesian tutorial, and settings escape hatch", async () => {
  render(<OnboardingHome client={missingRuntimeClient} locale="id" projects={[]} snapshot={missingRuntimeSnapshot}
    onOpenProject={vi.fn()} onStartProject={vi.fn()} onOpenSettings={vi.fn()} />);

  expect(await screen.findByRole("button", { name: "Perbaiki setup wajib" })).toBeVisible();
  expect(screen.getByText("Impor video")).toBeVisible();
  expect(screen.getByRole("button", { name: "Buka detail performa" })).toBeVisible();
});

test("repair completion refreshes readiness and keeps project resume available", async () => {
  // Emit running then completed job from watchJob and assert Resume remains available.
});
```

- [ ] **Step 2: Run Home tests and verify failure**

Run (from `web/`): `npm.cmd run test -- src/OnboardingHome.test.tsx`

Expected: FAIL because `OnboardingHome` does not exist.

- [ ] **Step 3: Implement Home as action-first UI**

```tsx
export function OnboardingHome({ client, locale, projects, snapshot, onOpenProject, onStartProject, onOpenSettings }: Props) {
  const repair = () => watchSetupJob(client, client.repairRequiredSetup, refreshSnapshot);
  return <main>
    <ReadinessCard action={snapshot.recommended_action} onRepair={repair} />
    <PerformanceSummary profile={snapshot.preferences.performance_profile} onOpenSettings={onOpenSettings} />
    <TutorialChecklist steps={snapshot.tutorial_steps} />
    <ProjectActions projects={projects} onStartProject={onStartProject} onOpenProject={onOpenProject} />
  </main>;
}
```

Use short Indonesian default copy: `Mulai proyek`, `Lanjutkan proyek`, `Perbaiki setup wajib`, `Otomatis`, `CPU`, `GPU`. Keep details collapsed until user requests them. Do not show raw tracker engine labels on Home. Build visual state from server snapshot, not local boolean guesses.

- [ ] **Step 4: Run Home and full frontend type checks**

Run (from `web/`): `npm.cmd run test -- src/OnboardingHome.test.tsx src/StudioApp.test.tsx`

Run (from `web/`): `npm.cmd run check`

Expected: PASS.

- [ ] **Step 5: Commit guided Home**

```bash
git add web/src/OnboardingHome.tsx web/src/OnboardingHome.test.tsx web/src/App.tsx web/src/styles.css
git commit -m "feat: add guided studio home"
```

## Task 7: Implement Performance Settings and Advanced Controls

**Files:**
- Create: `web/src/PerformanceSettings.tsx`
- Create: `web/src/PerformanceSettings.test.tsx`
- Modify: `web/ux/AccelerationCenter.tsx`
- Modify: `web/src/App.tsx`
- Modify: `web/src/styles.css`
- Modify: `web/ux/setup.css`
- Modify: `web/ux/AccelerationCenter.test.tsx`

**Interfaces:**
- Consumes onboarding snapshot/preferences, acceleration status/plans, and project acceleration APIs.
- Produces profile actions `updatePreferences({ performance_profile: "auto" | "cpu" | "gpu" })`, repair/retry actions, and optional `Advanced engine controls` disclosure.

- [ ] **Step 1: Write failing profile/error UI tests**

```tsx
test("GPU profile explains missing live evidence and offers repair without claiming ready", async () => {
  render(<PerformanceSettings client={gpuMissingClient} locale="id" />);

  await user.click(screen.getByRole("button", { name: "Gunakan GPU" }));
  expect(await screen.findByText("Inferensi YuNet CUDA belum terverifikasi")).toBeVisible();
  expect(screen.getByRole("button", { name: "Perbaiki GPU" })).toBeVisible();
});

test("research model still needs acknowledgement in advanced settings", async () => {
  render(<PerformanceSettings client={researchPlanClient} locale="en" />);
  await user.click(screen.getByRole("button", { name: "Install SCRFD" }));
  expect(screen.getByRole("button", { name: "Download model" })).toBeDisabled();
});
```

- [ ] **Step 2: Run settings tests and verify failure**

Run (from `web/`): `npm.cmd run test -- src/PerformanceSettings.test.tsx ux/AccelerationCenter.test.tsx`

Expected: FAIL because `PerformanceSettings` does not exist.

- [ ] **Step 3: Implement simple profiles before advanced controls**

```tsx
function ProfileChooser({ value, onSelect }: { value: PerformanceProfile; onSelect: (profile: PerformanceProfile) => Promise<void> }) {
  return <div role="radiogroup">
    {(["auto", "cpu", "gpu"] as const).map((profile) => <button role="radio" aria-checked={value === profile} onClick={() => onSelect(profile)}>{label(profile)}</button>)}
  </div>;
}
```

Show per-stage evidence below the selected profile: tracker provider/model/live result and encoder smoke result. `GPU` response errors show server recovery action plus retry. Move `AccelerationCenter` behind an `Advanced engine controls` disclosure; it remains the only place where explicit YuNet, MediaPipe, SCRFD, RetinaFace, NVENC, and licence acknowledgement can be chosen.

When project-level tracker change occurs, preserve existing backend behavior: clear candidate tracks/subject lock/preview only. Encoder-only change clears preview only. Do not duplicate invalidation in React.

- [ ] **Step 4: Run profile/UI regression tests**

Run (from `web/`): `npm.cmd run test -- src/PerformanceSettings.test.tsx ux/AccelerationCenter.test.tsx src/OnboardingHome.test.tsx`

Run (from `web/`): `npm.cmd run check`

Expected: PASS.

- [ ] **Step 5: Commit performance settings**

```bash
git add web/src/PerformanceSettings.tsx web/src/PerformanceSettings.test.tsx web/ux/AccelerationCenter.tsx web/ux/AccelerationCenter.test.tsx web/src/App.tsx web/src/styles.css web/ux/setup.css
git commit -m "feat: simplify performance setup"
```

## Task 8: Remove Split Entrypoints, Document, and Verify End-to-End

**Files:**
- Delete: `web/ux/main.tsx`
- Delete: `web/ux/SetupStudio.tsx`
- Delete: `web/ux/SetupStudio.ts`
- Delete: `web/ux/SetupStudioImpl.ts`
- Delete: `web/ux/SetupStudioImpl.tsx`
- Delete: `web/ux/SetupStudioImpl.js`
- Delete: `web/ux/SetupStudio.test.tsx`
- Modify: `web/tsconfig.app.json`
- Modify: `README.md`
- Modify: `SETUP_CENTER.md`
- Modify: `CONTRIBUTING.md`
- Modify: `web/package.json`
- Create: `web/playwright.config.ts`
- Create: `web/e2e/home-to-export.spec.ts`
- Create: `tests/browser_smoke_server.py`
- Modify: `tests/test_web_launch.py`
- Test: `tests/test_full_studio_api.py`, `tests/test_tracking_render_integration.py`, `tests/test_nvenc.py`, `tests/test_gpu_smoke.py`

**Interfaces:**
- Consumes one built `autoclip/web/static/index.html` entry from Task 4.
- Produces documented user command `autoclip web`, documented source asset build, and no remaining active `ux.html`/two-build route.
- Produces `npm.cmd run test:browser` from `web/`, which starts only a local fake-pipeline FastAPI fixture and exercises real browser navigation/WebSocket job updates.

- [ ] **Step 1: Write failing release-path regression tests**

```python
def test_packaged_static_app_serves_home_entry(tmp_path: Path) -> None:
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<div id='root'></div>", encoding="utf-8")

    app = create_usable_studio(tmp_path / "projects", dist=static)
    assert TestClient(app).get("/").status_code == 200
```

```ts
test("new user imports, selects subject, approves, and exports", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Mulai proyek" }).click();
  await page.locator('input[type="file"]').setInputFiles({ name: "source.mp4", mimeType: "video/mp4", buffer: Buffer.from("fixture") });
  await page.getByRole("button", { name: "Analisis klip" }).click();
  await page.getByRole("button", { name: "Pilih subjek" }).click();
  await page.getByRole("button", { name: "Buat pratinjau" }).click();
  await page.getByRole("button", { name: "Setujui pratinjau" }).click();
  await expect(page.getByRole("button", { name: "Ekspor 9:16" })).toBeEnabled();
})
```

- [ ] **Step 2: Run release-path test and verify failure before old entry removal**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_web_launch.py tests/test_usable_studio.py -q`

Expected: FAIL until server no longer requests `ux.html` and browser test fixture exists.

- [ ] **Step 3: Remove obsolete setup entrypoints and update docs**

Remove only modules listed above after imports/tests use new app shell. Remove their exclusions from `web/tsconfig.app.json` and references to separate Vite configs/`ux.html`.

Document exact user flow:

```powershell
autoclip web
# Browser opens Home. Use Perbaiki setup wajib only when Home names a blocker.
```

Document contributor asset build separately:

```powershell
cd web
npm.cmd ci
npm.cmd run build
```

Describe CPU as valid, GPU checks as live evidence, optional research model acknowledgement, and no silent fallback. Do not instruct end users to run Vite or manually inspect CUDA merely to launch Studio.

Add `@playwright/test` as a development dependency and a `test:browser` script. `tests/browser_smoke_server.py` must create an isolated `create_usable_studio()` application with fake pipeline/tracking services that persist a candidate, selected subject, preview-ready state, and export artifact through the real HTTP/WebSocket APIs. `web/playwright.config.ts` starts that fixture on localhost and points Chromium at it. The browser test imports a synthetic MP4 payload and waits for visible terminal job state between each action; it must not mock browser requests or bypass the approval button.

- [ ] **Step 4: Run complete verification suite**

Run: `./.venv/Scripts/python.exe -m pytest -q`

Run (from `web/`): `npm.cmd run test`

Run (from `web/`): `npm.cmd run check`

Run (from `web/`): `npm.cmd run build`

Run (from `web/`): `npm.cmd run test:browser`

Run: `./.venv/Scripts/python.exe -m pytest tests/test_web_launch.py tests/test_full_studio_api.py tests/test_tracking_render_integration.py tests/test_nvenc.py -q`

Expected: all PASS. Run `tests/test_gpu_smoke.py` only with `AUTOCLIP_RUN_GPU_SMOKE=1` on a machine with the intended GPU.

- [ ] **Step 5: Commit documentation and removal**

```bash
git add -u web/ux web/tsconfig.app.json README.md SETUP_CENTER.md CONTRIBUTING.md tests/test_web_launch.py tests/test_usable_studio.py
git commit -m "docs: document guided local studio"
```

## Plan Self-Review

- Spec coverage: Tasks 1-3 implement durable preferences, readiness, safe repair, explicit profiles, and structured failures. Task 4 implements canonical no-rebuild launch and packaged assets. Tasks 5-7 implement Home, tutorial, settings, locale, retry, and advanced controls. Task 8 covers migration cleanup, docs, release verification, and existing tracking invariants.
- Placeholder scan: no unfinished markers, deferred implementation language, or undefined task references remain. Every planned external interface is introduced in Task 1-5 before consumer tasks.
- Type consistency: `PerformanceProfile`, `AppPreferences`, `OnboardingSnapshot`, `StudioClient`, `OnboardingService`, `ProfileUnavailable`, and `run_web` use the same names in all tasks.
