# AutoClip Local Web Studio

Launch with `autoclip web` (or `autoclip-web-studio.bat`). AutoClip starts the local FastAPI server, serves packaged static assets, and opens the default browser at `http://127.0.0.1:8765`.

Launch never builds with Vite or requires Node.js. Projects live in `~/.autoclip/projects/`; uploaded sources are copied into their project so a browser restart does not lose edit state.

The workflow is intentionally one project and one heavy local job at a time:

1. Import an MP4, MOV, M4V, MKV, AVI, or WebM file (or an HTTP(S) video URL).
2. Analyze it for candidates.
3. Request tracking. The detector produces candidates without selecting the highest-confidence face automatically.
4. Lock a subject, render a preview, then approve it.
5. Export the approved 1080×1920 MP4.

Home is Indonesian by default; use `EN` to persist English. Choose Auto, CPU, or GPU in Performa. GPU only becomes selected when its tracker and NVENC have live evidence. If required setup is missing, Home offers one fixed local repair flow; it never opens an arbitrary command prompt.

The runtime panel checks FFmpeg, OpenCV, MediaPipe Tasks, the bundled detector model, and whether CPU or GPU execution is active. If tracking is unavailable or the subject is lost, AutoClip reports it and never silently substitutes a center crop.

For UI development only, run `npm.cmd run dev` in `web/` alongside `python -m autoclip.web.studio_server`; production assets are created with `npm.cmd run build` and written to `autoclip/web/static/`.
