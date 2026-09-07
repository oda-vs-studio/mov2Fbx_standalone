@echo off
setlocal
pushd "%~dp0"
set "PYTHONUTF8=1"
if defined M2A_PYTHON (
  "%M2A_PYTHON%" -m tools.setup_camera %*
) else (
  python -m tools.setup_camera %*
)
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" echo Camera setup failed. Existing body environment and models are preserved.
if not defined M2A_SETUP_NO_PAUSE pause
popd
exit /b %RESULT%
