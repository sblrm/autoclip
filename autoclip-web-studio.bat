@echo off
setlocal
if exist "%~dp0.venv\Scripts\python.exe" (
  "%~dp0.venv\Scripts\python.exe" -m autoclip.cli web
) else (
  autoclip web
)
exit /b %errorlevel%
