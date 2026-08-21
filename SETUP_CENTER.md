# AutoClip Local Studio

Run this from an installed AutoClip environment:

```powershell
autoclip web
```

Browser opens Home at localhost automatically. It checks local readiness, resumes projects, imports one video, and opens Settings only when needed. End users do not need Node, Vite, or a batch launcher.

## What it can repair

- **FFmpeg**: Windows uses fixed WinGet arguments; Ubuntu uses fixed `pkexec apt-get install -y ffmpeg` arguments.
- **OpenCV and MediaPipe**: AutoClip installs the packages into its active Python environment.
- **Whisper**: AutoClip installs the local transcription package into its active Python environment.
- **PyTorch CPU**: AutoClip installs the fixed CPU wheel when the required runtime is missing.
- **Ollama**: optional local analysis, installed through Windows Package Manager.

Every install starts from a button click. The server accepts only a fixed set of installer plans. It never receives or runs a command entered in the browser.

## CPU and GPU

CPU mode is always supported. It is not an error. Auto chooses a verified CPU tracker with `libx264` when GPU evidence is unavailable. Explicit GPU never silently downgrades: it requires live tracker inference and NVENC smoke evidence, or returns a repair action.

Runtime status stays separate for Whisper, ONNX Runtime, each face engine, and each FFmpeg encoder. One green GPU badge never implies every stage uses GPU.

For a Windows RTX 5070, current PyTorch CUDA can work without installing CUDA Toolkit solely for AutoClip. In **Performa**, the visible **Setup GPU tracking** checklist offers fixed buttons for PyTorch CUDA 12.8, `onnxruntime-gpu[cuda,cudnn]==1.26.0`, and the pinned YuNet model. Install each needed component, restart after PyTorch when asked, then use **Cek ulang GPU**. Recheck must pass live `CUDAExecutionProvider` inference before `yunet_cuda` becomes ready and Auto selects it. FFmpeg NVENC requires a successful `h264_nvenc` smoke encode, not merely an entry in `ffmpeg -encoders`.

Windows GPU face tracking uses YuNet CUDA. MediaPipe GPU is supported only on Ubuntu and must pass live VIDEO inference. CPU-only systems remain valid: Auto chooses a ready CPU MediaPipe/YuNet tracker and `libx264`, without a false GPU-ready badge.

YuNet uses MIT-licensed model assets. InsightFace SCRFD and RetinaFace model packs are optional, research-only/non-commercial assets; Setup Center requires acknowledgement before download. All face detection runs locally, without recognition or embeddings.

GPU runtime packages are substantial and require internet access. Install only the component requested by the displayed repair plan, then restart and Recheck.

## First project

1. From Home, use **Perbaiki setup wajib** only when it names a required blocker. For optional GPU tracking components, open **Performa** and follow **Setup GPU tracking** instead.
2. Choose **Mulai proyek** and import one local video or supported URL.
3. Analyze candidates, select and lock one face track, then build a tracking preview.
4. Approve the preview before exporting the 9:16 MP4.

If an install fails, Studio retains the job result locally. Open Settings for evidence and retry its fixed repair plan.

## Manual hardware matrix

| Machine | Required evidence |
|---|---|
| Windows RTX 5070 | `yunet_cuda` ready with `CUDAExecutionProvider`; selected subject remains locked in preview; approved MP4 uses `h264_nvenc`; artifact metadata names tracker and encoder. |
| Ubuntu NVIDIA | `mediapipe_gpu` ready only after live VIDEO inference; repeat subject-lock, gap, preview, and export checks. |
| CPU-only | GPU states explain why unavailable; Auto uses a CPU tracker plus `libx264`; no false GPU badge. |

For every machine, compare saved preview and export trajectory `centers` and selected face-track ID; they must match. Force face loss, confirm persisted gap, and review hold-then-ease-to-center behavior before approval.
