# AutoClip Setup Center

Run this from the repository root on Windows:

```powershell
.\autoclip-setup-studio.bat
```

Open http://127.0.0.1:8765. The Setup Center checks your local machine before the editor opens.

## What it can repair

- **FFmpeg**: Windows Package Manager installs `Gyan.FFmpeg.Shared` after you press Install.
- **OpenCV and MediaPipe**: AutoClip installs the packages into its active Python environment.
- **Whisper**: AutoClip installs the local transcription package into its active Python environment.
- **Ollama**: optional local analysis, installed through Windows Package Manager.

Every install starts from a button click. The server accepts only a fixed set of installer plans. It never receives or runs a command entered in the browser.

## CPU and GPU

CPU mode is always supported. It is not an error.

When an NVIDIA adapter is detected but PyTorch is CPU-only, Setup Center offers **Enable NVIDIA GPU for Whisper**. It reinstalls the active PyTorch version from the official CUDA 13.0 wheel index, then requires an AutoClip restart and recheck. It does not claim that face tracking or FFmpeg rendering also moved to GPU. Their status stays separate.

The CUDA installation is substantial and requires internet access. Read the displayed status and only start it when GPU transcription is wanted.

## First project

1. Repair every required component or use the Recheck button.
2. Enter studio and import one local video or a supported URL.
3. Analyze candidates, select and lock one face track, then build a tracking preview.
4. Approve the preview before exporting the 9:16 MP4.

If an install fails, Setup Center retains the job result in its local job history. Retry the same component after fixing the stated cause.
