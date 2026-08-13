# AutoClip Local Web Studio

Launch from Windows with `autoclip-web-studio.bat`, then open `http://127.0.0.1:8765`.

The launcher builds `web/` and starts the local FastAPI server. Projects live in `~/.autoclip/projects/`; uploaded sources are copied into their project so a browser restart does not lose edit state.

The workflow is intentionally one project and one heavy local job at a time:

1. Import an MP4, MOV, M4V, MKV, AVI, or WebM file (or an HTTP(S) video URL).
2. Analyze it for candidates.
3. Request tracking. The detector produces candidates without selecting the highest-confidence face automatically.
4. Lock a subject, render a preview, then approve it.
5. Export the approved 1080×1920 MP4.

The runtime panel checks FFmpeg, OpenCV, MediaPipe Tasks, the bundled detector model, and whether CPU or GPU execution is active. If tracking is unavailable or the subject is lost, AutoClip reports it and never silently substitutes a center crop.

For UI development, run `npx vite --config studio.vite.config.ts` in `web/` alongside `python -m autoclip.web.studio_server`. The Vite proxy forwards `/api` to port 8765.
