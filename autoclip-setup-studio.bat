@echo off
setlocal

pushd "%~dp0web"
call ".\node_modules\.bin\vite.cmd" build --config ".\studio.vite.config.ts"
set "studioBuildExit=%errorlevel%"
if not "%studioBuildExit%"=="0" (
  popd
  exit /b %studioBuildExit%
)

call ".\node_modules\.bin\vite.cmd" build --config ".\setup.vite.config.ts"
set "setupBuildExit=%errorlevel%"
popd
if not "%setupBuildExit%"=="0" exit /b %setupBuildExit%

"%~dp0.venv\Scripts\python.exe" -m autoclip.web.usable_studio
