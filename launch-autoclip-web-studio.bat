@echo off
setlocal
pushd "%~dp0web"
call ".\node_modules\.bin\vite.cmd" build --config ".\studio.vite.config.ts"
set "studioBuildExit=%errorlevel%"
popd
if not "%studioBuildExit%"=="0" exit /b %studioBuildExit%
"%~dp0.venv\Scripts\python.exe" -m autoclip.web.layout_fixed_studio
