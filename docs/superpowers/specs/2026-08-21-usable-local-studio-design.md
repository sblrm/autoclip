# AutoClip Usable Local Studio Design

**Status:** Approved design

## Problem

AutoClip already has a local Studio, setup checks, model installers, a serial job runner, and GPU probes. UX still exposes these as separate technical systems:

- `autoclip web` delegates to a batch launcher that rebuilds two Vite targets before every launch and does not open a browser.
- Setup and editor switch through browser-only React state, so refresh returns to setup instead of the user's work.
- Required setup is independent component cards rather than one guided repair action.
- CPU/GPU choice is raw detector/encoder names before a user knows whether their machine can use them.

## Goals

1. `autoclip web` launches one local app, waits for readiness, and opens the browser.
2. Home is durable first-run onboarding and project resume.
3. Users repair missing supported prerequisites in-app through one primary repair action with transparent progress.
4. `Auto`, `CPU`, and `GPU` are understandable task-level choices. GPU requires a live task-specific check.
5. Preserve local-only storage, serial jobs, allow-listed installers, licence acknowledgement, subject lock, and existing CLI support.
6. Package built web assets for releases. Normal launches never need Node or rebuild frontend.

## Non-goals

- Cloud accounts, telemetry, remote processing, arbitrary shell commands.
- Batch queues, social publishing, new output formats, face recognition.
- Claiming GPU support from hardware, CUDA Toolkit, or FFmpeg encoder-list presence alone.

## User Journey

Normal journey:

`Home` -> `Start project` -> `Import video` -> `Analyze` -> `Choose subject` -> `Preview` -> `Approve and export`

Home is always valid. Missing dependencies block only affected actions, never access to Home, prior projects, or Settings.

### Home

Home contains only decisions needed now:

- `Start project`, then `Resume project` when unfinished work exists.
- Live readiness summary. Missing required setup has primary action `Repair required setup`; details are expandable.
- Performance card: `Auto` default, plus `CPU` and `GPU`.
- Live tutorial checklist from project state: prepare, import, analyze, lock subject, preview, approve, export.

Versions, models, detector engines, encoder probes, logs, and individual retries move to `Settings > Performance`.

### Navigation and persistence

React has routes for Home, project, and Settings. It does not use in-memory `showEditor`. Refresh restores current route, latest project, and onboarding state.

SQLite gets a small `app_preferences` table for language, last project, onboarding state, and default performance profile. Project stages and existing project acceleration remain project-owned. Derived readiness is server-owned, never trusted from browser storage.

## Readiness and Repair

### Readiness model

One server onboarding payload composes SetupManager, acceleration manager, project store, and job store. It returns required/optional components, hardware and verified capabilities, recommended profile, blockers for next action, and active/recent setup jobs.

State remains precise: `missing`, `installing`, `ready`, `unsupported`, `failed`. Installed runtime and verified GPU capability are separate states.

### Repair job

`Repair required setup` starts one durable serial job. At execution, server recalculates missing requirements and runs only fixed allow-listed plans in dependency order. It streams each child step through existing job WebSocket, rechecks immediately usable components, and persists final status/error.

Browser never supplies command, package URL, or executable path. Before download, UI shows component, source, effect, restart/admin confirmation, and model licence conditions.

Individual repair/retry remains in Settings. Failed batch stops at failed child, preserves completed work, then retries only remaining work.

### Platform installers

- Windows FFmpeg/Ollama: fixed WinGet plans. Python packages: active AutoClip Python environment.
- Ubuntu FFmpeg: fixed system plan through platform privilege dialog. Missing polkit/admin access gives structured recovery; browser never accepts passwords.
- OpenCV, MediaPipe, Whisper, ONNX Runtime, and models: fixed plans in AutoClip runtime. Models install below local model root with size/checksum validation.

## Performance and Face Tracking

### User profiles

`Auto` is default: choose verified GPU where useful, else verified CPU.

`CPU`: use ready CPU tracker and `libx264`.

`GPU`: explicit request. Missing/failed live evidence starts relevant repair flow. It never silently changes to CPU or center crop.

Default profile applies to new projects. Existing projects retain saved tracker/encoder selection. Advanced Settings exposes explicit engines/encoders for expert users.

### GPU evidence

Windows NVIDIA face tracking: YuNet with ONNX Runtime `CUDAExecutionProvider`; valid only after live inference with pinned model.

Ubuntu NVIDIA: MediaPipe GPU valid only after live VIDEO-mode inference.

NVENC valid only after real `h264_nvenc` smoke encode.

YuNet is standard recommendation. InsightFace SCRFD and RetinaFace stay optional research-only installs, require licence acknowledgement, and are never part of required repair batch. Subject lock, gaps, and saved preview trajectory remain existing invariants.

## Application and Launch Architecture

### One build

Home, Studio, and Settings are one React app served by setup-aware FastAPI. One Vite production build replaces separate setup/editor builds. Release assets are copied into package data and GitHub release artifacts.

Contributors build assets with Node. End users running installed package/release do not need Node, do not run Vite, and do not wait for frontend rebuild at startup.

### Launcher

`autoclip web` is canonical. It starts local server, waits for health, opens default browser once, and remains foreground until interrupted. Port collision follows safe local-port policy and reports actual URL.

Existing batch files become compatibility wrappers for `autoclip web`; they no longer build Vite. Source checkout without built assets shows clear developer-build recovery, never a blank page.

### Boundaries

- `OnboardingService`: readiness, tutorial state, profile preference, next-action decision.
- `SetupManager`: fixed install plans and machine probes.
- `AccelerationManager`: live tracker/encoder evidence.
- `SetupBatchService`: serial required repair composition/execution.
- Project store: media, clips, per-project acceleration, artifacts, jobs.

Errors have stable code, human title, recovery action, retryability, and related job/component IDs. UI shows concise result first and expandable logs second.

## Validation

Backend tests cover preferences/route resume, readiness composition, batch ordering, skip-ready, failed-child resume, no arbitrary command, Windows/Ubuntu installer choice, permission/restart errors, model integrity/licence, explicit GPU rejection without live evidence, and existing tracking/NVENC invariants.

Frontend/browser tests cover Home first run, refresh/resume, Indonesian/English copy, live tutorial, repair confirmation/progress/failure/retry, profile explanations, advanced settings, and import through approved export.

Release test builds single bundle, validates package data, launches `autoclip web`, waits for health, and smoke-tests Home without Node/Vite at runtime.

## Acceptance Criteria

1. New user can run `autoclip web`, repair supported missing prerequisites, import, and finish approved export without leaving app for setup instructions.
2. CPU-only user can complete same flow with CPU clearly valid.
3. GPU user sees installed state, missing downloads, and real tracker/NVENC verification.
4. Refresh preserves navigation, setup progress, project, and job history.
5. Browser cannot execute arbitrary commands. Explicit GPU never silently becomes CPU/center crop.
