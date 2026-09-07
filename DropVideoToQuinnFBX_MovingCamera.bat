@echo off
setlocal
chcp 65001 >nul
pushd "%~dp0"
if "%~1"=="" (
  echo Drop one or more videos onto this BAT.
  echo Output: same folder and filename as video, with .fbx extension.
  echo Auto 1/2 people; shared positions; initial feet planted; 12+ frames; full length. Existing FBX files are not overwritten.
  if not defined M2A_NO_PAUSE pause
  popd
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo Python environment is missing. Run SetupStandalone.bat first.
  if not defined M2A_NO_PAUSE pause
  popd
  exit /b 1
)
".venv\Scripts\python.exe" -u -m m2a.drop_video --moving-camera %*
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" echo Failed. See the error above; partial results remain in runs\drop.
if not defined M2A_NO_PAUSE pause
popd
exit /b %RESULT%
