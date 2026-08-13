# AutoClip GPU Acceleration Design

## Goal

Make GPU acceleration a trustworthy local AutoClip feature: Auto chooses the fastest verified encoder and face-tracking engine, users can inspect or override that choice, and dependency/model downloads occur only after an explicit user action.

## Scope

- NVIDIA GPU support on Windows and Ubuntu.
- FFmpeg NVENC for H.264 and HEVC export.
- Commercial-safe YuNet ONNX face detector as the default Windows GPU tracker.
- MediaPipe Tasks CPU tracking everywhere and GPU tracking only on Ubuntu after a live capability probe.
- Research-only optional InsightFace RetinaFace and SCRFD installs after an explicit license acknowledgement.
- CPU fallback for AMD/Intel/unknown systems with exact status, never a false GPU claim.

## Out of scope

- AMD AMF, Intel Quick Sync, DirectML, Apple Metal, cloud processing, face recognition, and any silent model or package download.

## Platform policy

| Environment | Auto face-tracking engine | Export encoder |
|---|---|---|
| Windows + verified NVIDIA CUDA ONNX Runtime | YuNet with `CUDAExecutionProvider` | `h264_nvenc` when FFmpeg exposes it |
| Ubuntu + verified MediaPipe GPU delegate | MediaPipe Tasks GPU | `h264_nvenc` when FFmpeg exposes it |
| Ubuntu + NVIDIA CUDA ONNX Runtime, no MediaPipe delegate | YuNet with `CUDAExecutionProvider` | `h264_nvenc` when FFmpeg exposes it |
| Any other environment | MediaPipe CPU or YuNet CPU | `libx264` |

The resolver uses a working-runtime probe rather than GPU hardware presence. A selected engine must create a detector/session and run one inference before it is reported as ready.

## Face-tracking engines

### Auto

`Auto` is the default. It selects a verified platform-specific engine, persists the selected engine, model, provider, and trajectory in the project, and uses that exact trajectory for both preview and final export.

### Commercial-safe engine: YuNet

YuNet is the default ONNX model. It is sourced only from a pinned OpenCV Zoo release URL, checked against a pinned SHA-256, and stored under `~/.autoclip/models/yunet/`. Its UI label includes model version, license, source, provider, and CPU/GPU result. OpenCV Zoo's YuNet directory is MIT licensed.

### MediaPipe Tasks

MediaPipe remains the default CPU detector on systems where it is available. On Ubuntu only, the setup probe may offer `MediaPipe GPU`; it constructs `BaseOptions(delegate=Delegate.GPU)`, enters `FaceDetector` in VIDEO mode, and runs an ordered test frame. A failure leaves it unavailable and records the error; it must not center-crop or silently use CPU when the user explicitly selected GPU.

### InsightFace research engines

`SCRFD` and `RetinaFace` are visible as optional research-only choices. Each card states that the InsightFace code is MIT while pretrained model assets are restricted to non-commercial research. The install flow requires an acknowledgement checkbox and saves this acknowledgement with timestamp, selected model, and source. It downloads only known pinned package/release sources and records checksum and license metadata. These engines are never Auto defaults.

## Tracking behavior

All engines yield normalized boxes/centres into the existing deterministic spatial track matcher. The user locks one `FaceTrack`; gaps remain gaps; hold-then-ease-to-centre behavior remains persisted in the saved trajectory. A no-face result means `no_faces`, not a hidden static crop. Export remains blocked until tracking preview approval.

## NVENC export

Setup probes `ffmpeg -hide_banner -encoders` for `h264_nvenc` and `hevc_nvenc`, then performs a minimal local encoder smoke test before reporting either ready. Export modes are `auto`, `h264_nvenc`, `hevc_nvenc`, and `libx264`.

`auto` chooses H.264 NVENC when verified, otherwise CPU H.264. An explicit NVENC selection never changes to CPU without a structured error. It keeps `nvenc_error`, offers recheck/retry, and preserves the user's choice. Encoder metadata is stored on every artifact and shown in export history.

## Setup Center UX

Add a GPU Acceleration section:

1. hardware and driver status;
2. runtime probes by component: Whisper, face tracker, ONNX provider, MediaPipe delegate, FFmpeg encoder;
3. Auto recommendation plus manual selector;
4. fixed, reviewable package/model plans with size/license/source/checksum;
5. explicit install/download action, durable job progress, failure explanation, recheck, and retry;
6. a short benchmark and final verified state.

No endpoint accepts a browser-provided command, URL, package name, file path, or model identifier. All identifiers map to server-side allow-listed plans.

## Configuration and interfaces

Introduce stable identifiers:

- tracker engines: `auto`, `mediapipe_cpu`, `mediapipe_gpu`, `yunet_cpu`, `yunet_cuda`, `scrfd_cpu`, `scrfd_cuda`, `retinaface_cpu`, `retinaface_cuda`;
- encoder modes: `auto`, `h264_nvenc`, `hevc_nvenc`, `libx264`;
- runtime states: `ready`, `missing`, `unsupported`, `failed`, `requires_acknowledgement`.

Existing `use_mediapipe` config remains readable. Its value maps to `mediapipe_cpu`; `False` maps to `auto` unless a legacy static-crop option was explicitly selected. New projects default to `auto` tracker and `auto` encoder.

The API exposes status, allowed plans, install/download job creation, explicit selection, and artifact metadata. Project and clip records persist selected tracker/encoder and verification result. Project-owned model files and artifacts remain the only media paths served.

## Safety, privacy, and licensing

All detection and rendering stay local. No face recognition embeddings are created or stored. License acknowledgement is required before InsightFace model download. SHA-256 mismatch deletes the incomplete file and fails the job. User-provided local models are intentionally not part of this version.

## Test plan

- Resolver unit tests for Windows/Ubuntu/NVIDIA/CPU/unsupported combinations and failed runtime probes.
- ONNX Runtime CUDA provider preloading/session tests with mocks.
- MediaPipe GPU delegate option and failed probe tests.
- YuNet download checksum, cache, and detection-adapter tests.
- InsightFace acknowledgement, pinned source, and research-only gating tests.
- NVENC parser, encoder smoke, Auto choice, explicit-NVENC failure, and artifact metadata tests.
- Existing multi-subject lock/gap/crop-bound/preview-export trajectory tests run against each adapter contract.
- FastAPI plan validation, job lifecycle, and no-arbitrary-input tests.
- React tests for Auto recommendation, manual override, research license gate, engine-specific status, retries, and bilingual copy.
- Browser smoke: new setup, GPU probe, YuNet install, Auto tracking preview, approval, NVENC export; unsupported system CPU fallback.

## Verification targets

- full Python suite;
- frontend TypeScript check and test suite;
- production builds for editor and Setup Center;
- Windows NVIDIA smoke against a real CUDA ONNX Runtime session and NVENC-enabled FFmpeg;
- Ubuntu MediaPipe GPU smoke on supported hardware;
- CPU-only smoke proving clear fallback and no false GPU claim.
