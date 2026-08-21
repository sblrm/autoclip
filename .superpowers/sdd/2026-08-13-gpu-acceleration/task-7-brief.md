# Task 7 brief — bilingual acceleration controls

Implement only Task 7 from `docs/superpowers/plans/2026-08-13-gpu-acceleration.md`.

## Scope

Create:

- `web/ux/AccelerationCenter.tsx`
- `web/ux/AccelerationCenter.test.tsx`
- `web/src/AccelerationControls.test.tsx`

Modify:

- `web/src/api.ts`
- `web/ux/SetupStudio.tsx`
- `web/src/App.tsx`
- `web/ux/setup.css`

Do not change Python/backend contracts. Do not use browser supplied commands, URLs, or package names.

## Existing API contract

Task 6 routes are fixed:

- `GET /api/acceleration/status` and `POST /api/acceleration/recheck` return `{ platform, engines, encoders }`, with maps keyed by exact IDs.
- `GET /api/acceleration/plans` returns public metadata only: `id`, `label`, `kind`, `requires_restart`, `detail`, `license`, `research_only`, optional `bytes`. Never command/source URL.
- `POST /api/acceleration/install` body is only `{ plan_id, acknowledge_research_license? }`; returns `{ job_id }` with HTTP 202. Only valid plan ids: `onnxruntime_cuda_128`, `yunet_2023mar`, `insightface_buffalo_m_retinaface`, `insightface_antelopev2_scrfd`.
- `PATCH /api/projects/{id}/acceleration` body only `{ tracker_engine?, encoder_mode? }`; validates/resolves first. It returns project acceleration `{ project_id, tracker_engine, encoder_mode }`.
- project detail includes top-level `acceleration` plus every clip can have `tracking_resolution`.
- artifacts can carry `metadata`, including `encoder` and `tracker_engine`.

Exact tracker IDs: `auto`, `mediapipe_cpu`, `mediapipe_gpu`, `yunet_cpu`, `yunet_cuda`, `scrfd_cpu`, `scrfd_cuda`, `retinaface_cpu`, `retinaface_cuda`. Exact encoder IDs: `auto`, `h264_nvenc`, `hevc_nvenc`, `libx264`. Runtime state IDs: `ready`, `missing`, `unsupported`, `failed`, `requires_acknowledgement`.

Probe fields come from Python dataclass serialization. Preserve optional fields safely: state, provider, model_id, reason/probe_detail/error_code/error. Do not invent a server type requirement beyond tolerant UI typing.

## UI requirements

- Existing UI is Indonesian default; preserve switch to English.
- `AccelerationCenter` accepts injected client, `locale`, optional `projectId`, and optional post-selection callback if needed. Export types useful to tests.
- Render Auto selection first, with exact recommendation/reason/provider/model/encoder evidence. Windows priority is YuNet CUDA when ready; otherwise the API state must be presented, never claimed GPU-ready from hardware alone.
- Render independent component evidence for Whisper, ONNX Runtime, MediaPipe GPU, YuNet, FFmpeg encoder. Replace old GPU Whisper-only presentation in `SetupStudio`.
- Render valid manual tracker/encoder choices. Each choice must say CPU/GPU, live verification state, provider/model/reason. Recheck/retry is available.
- Model installs use fixed listed plans only. Research plans use a Radix dialog; show exact English research message `Model assets are for non-commercial research only.` and disable `Download model` until acknowledgement checkbox. Indonesian text: `Aset model hanya untuk riset non-komersial.` and `Saya memahami batas lisensi model ini.`
- Required status words: ID `Otomatis`, `Rekomendasi`, `Terverifikasi dengan inferensi nyata`, `Belum terverifikasi`; EN `Auto`, `Recommended`, `Verified by live inference`, `Not verified`.
- App inspector: acceleration controls above subject selector. A selection calls `setProjectAcceleration`, refreshes project detail, leaves locked subject intact, marks current preview stale locally, and disables approval/export until a fresh preview completes. Do not mutate server preview status locally. Use a derived stale boolean rather than an effect when possible.
- Export history shows `artifact.metadata.encoder` and `artifact.metadata.tracker_engine` when available.
- Existing charcoal/signal-orange system only. No new gradients/shadow language. All actions minimum 44px and keyboard-focusable.

## Performance/React constraints

- Preserve `Promise.all` for independent initial calls.
- Do not create components inside render; use top-level components.
- Do not add broad/barrel imports or heavy dependencies. Radix dialog already installed.
- Avoid stale closures for WebSocket completion; cleanup sockets. Use `startTransition` for non-urgent detail refresh where current app does.

## Tests and verification

Begin tests red. At minimum prove:

1. Windows ready client shows `Rekomendasi: YuNet CUDA`; clicking Indonesian `Gunakan CPU MediaPipe` calls `setProjectAcceleration("project-1", { tracker_engine: "mediapipe_cpu" })`.
2. English research plan click `Install SCRFD` opens dialog, shows exact research warning, and `Download model` starts disabled.
3. App selection marks preview stale, keeps face-track lock, disables export until a new approved preview state is loaded; export history includes encoder/tracker metadata.

Run from `web`:

```powershell
npm.cmd run test -- --run ux/AccelerationCenter.test.tsx src/AccelerationControls.test.tsx ux/SetupStudio.test.tsx src/App.test.tsx
npm.cmd run check
npm.cmd run build
npx.cmd vite build --config studio.vite.config.ts
npx.cmd vite build --config setup.vite.config.ts
```

Fix existing TypeScript test global/config issues encountered within this command set. `web/src/App.ts` facade may be removed only if TypeScript confirms it is obsolete and `App.tsx` is canonical. No Git commands: this workspace is not a Git worktree.

Use `apply_patch` for all edits. Add report `task-7-report.md` with RED/GREEN commands/results and files changed.
