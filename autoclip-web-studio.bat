@echo off
setlocal
call "%~dp0web\node_modules\.bin\vite.cmd" build --config "%~dp0web\studio.vite.config.ts"
if errorlevel 1 exit /b %errorlevel%
"%~dp0.venv\Scripts\python.exe" -m autoclip.web.local_studio
