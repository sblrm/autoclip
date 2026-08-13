# Contributing to AutoClip

## Run the local studio

Windows contributors can use the same public entry point as end users:

```powershell
.\autoclip.bat web
```

The page at `http://127.0.0.1:8765` starts with Setup Center. It checks the
local runtime and exposes fixed repair plans for missing dependencies. Do not
add browser endpoints that accept arbitrary shell commands.

## Validate a change

```powershell
.\.venv\Scripts\python.exe -m pytest -q

cd web
.\node_modules\.bin\vite.cmd build --config .\studio.vite.config.ts
.\node_modules\.bin\vite.cmd build --config .\setup.vite.config.ts
npm run test -- --config setup.vite.config.ts
```

## UX expectations

- Local first: no account, cloud storage, or silent install action.
- Indonesian is the default UI language; English must remain usable.
- Runtime status is per engine. Never label the whole studio as GPU when only
  Whisper has CUDA.
- Face tracking must never silently switch to center crop when detection fails.
- Keep the approval gate before final export.

## Pull requests

Keep each change small and include test evidence. For UI work, include a
browser walkthrough of setup, import, tracking-subject selection, preview
approval, and export where practical.
