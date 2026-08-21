# Task 7 report — bilingual acceleration controls

## Outcome

- Added bilingual `AccelerationCenter` for live-verified tracker and encoder status, deterministic Auto recommendation, fixed install plans, recheck/retry, project overrides, and research-license acknowledgement.
- Setup Center now shows Whisper, ONNX Runtime, MediaPipe GPU, YuNet, and FFmpeg encoder independently instead of one global GPU/Whisper claim.
- Studio inspector now saves project acceleration above subject lock and gates approval/export while preview state is stale. Encoder-only changes preserve the locked subject; tracker-engine changes intentionally clear incompatible candidates and require a new explicit lock.
- Export history displays saved encoder and tracker metadata.
- Removed obsolete `App.ts`, `App.js`, and `App.mjs` facades so `App.tsx` is canonical.
- Added explicit frontend test cleanup and Vitest TypeScript globals/config typing.

## TDD evidence

RED:

```text
vitest run ux/AccelerationCenter.test.tsx src/AccelerationControls.test.tsx
FAIL: Failed to resolve import "./AccelerationCenter"
FAIL: Unable to find text "h264_nvenc"
```

GREEN required suite:

```text
npm.cmd run test -- --run ux/AccelerationCenter.test.tsx src/AccelerationControls.test.tsx ux/SetupStudio.test.tsx src/App.test.tsx
4 test files passed; 6 tests passed
```

Full frontend regression:

```text
npm.cmd run test
7 test files passed; 9 tests passed
```

## Verification

```text
npm.cmd run check
PASS

npm.cmd run build
PASS — 4627 modules transformed

npx.cmd vite build --config studio.vite.config.ts
PASS — 4627 modules transformed

npx.cmd vite build --config setup.vite.config.ts
PASS — 4629 modules transformed
```

## Files

Created:

- `web/ux/AccelerationCenter.tsx`
- `web/ux/AccelerationCenter.test.tsx`
- `web/src/AccelerationControls.test.tsx`

Modified:

- `web/src/api.ts`
- `web/src/App.tsx`
- `web/src/main.tsx`
- `web/src/styles.css`
- `web/src/test-setup.ts`
- `web/src/App.test.tsx`
- `web/src/StudioApp.test.tsx`
- `web/src/StudioSmoke.test.tsx`
- `web/src/StudioVerify.test.tsx`
- `web/ux/SetupStudio.tsx`
- `web/ux/SetupStudio.test.tsx`
- `web/ux/main.tsx`
- `web/ux/setup.css`
- `web/tsconfig.app.json`
- `web/vite.config.ts`

Removed obsolete facades:

- `web/src/App.ts`
- `web/src/App.js`
- `web/src/App.mjs`

## Reviewer correction — durable detection orchestration

The preview route now queues `tracking_detection` when the clip has no saved
tracking resolution. Detection remains explicit in `TrackingService.detect_tracks()`;
`render_preview()` still never performs an implicit detector fallback. After candidates
exist, the user must explicitly select a subject before a later preview job can produce
an approvable artifact.

Changing tracker engine clears only tracking candidates, gaps, trajectory/preview
artifacts, saved resolution, and the old subject lock. Final exports remain preserved.
Changing encoder only clears the stale preview and preserves detection candidates,
resolution, and the subject lock. The UI clears its stale gate only when refreshed
state contains a new `preview_ready` artifact whose tracker and encoder evidence match
the project selection; a detection-only completion cannot re-enable approval/export.

P2 corrections add a shared bilingual `SetupCopy`, include the active `ux` entry in
strict TypeScript checking, and give retry actions a 44px minimum target plus the shared
keyboard focus ring.

### Correction TDD evidence

RED backend:

```text
.\.venv\Scripts\python.exe -m pytest tests/test_acceleration_api.py -q
2 failed, 8 passed
- expected tracking_detection, received tracking_preview
- encoder-only change left stale tracking_preview artifact
```

RED frontend:

```text
npm.cmd run test -- --run src/AccelerationControls.test.tsx --pool forks --maxWorkers 1 --no-file-parallelism
1 failed: expected the required post-switch action; old UI still exposed Make preview
```

GREEN backend:

```text
.\.venv\Scripts\python.exe -m pytest tests/test_acceleration_api.py tests/test_full_store.py tests/test_full_studio_api.py tests/test_usable_studio.py -q
24 passed, 3 deprecation warnings
```

GREEN required frontend:

```text
npm.cmd run test -- --run ux/AccelerationCenter.test.tsx src/AccelerationControls.test.tsx ux/SetupStudio.test.tsx src/App.test.tsx --pool forks --maxWorkers 1 --no-file-parallelism
4 files passed; 6 tests passed
```

Full frontend regression:

```text
npm.cmd run test -- --run --pool forks --maxWorkers 1 --no-file-parallelism
7 files passed; 9 tests passed
```

Strict/build verification:

```text
npm.cmd run check
PASS (active src + ux entries)

npm.cmd run build
PASS — 4627 modules transformed

npx.cmd vite build --config studio.vite.config.ts
PASS — 4627 modules transformed

npx.cmd vite build --config setup.vite.config.ts
PASS — 4629 modules transformed
```

Correction files:

- `autoclip/web/full_store.py`
- `autoclip/web/studio_server.py`
- `tests/test_acceleration_api.py`
- `tests/test_full_studio_api.py`
- `web/src/api.ts`
- `web/src/App.tsx`
- `web/src/AccelerationControls.test.tsx`
- `web/src/styles.css`
- `web/ux/SetupStudio.tsx`
- `web/ux/SetupStudio.test.tsx`
- `web/ux/setup.css`
- `web/tsconfig.app.json`
