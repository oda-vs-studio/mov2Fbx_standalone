@echo off
setlocal
chcp 65001 >nul
pushd "%~dp0"
if "%~1"=="" (
  echo Drop one or more videos onto this BAT.
  echo Output: same folder and filename as video, with .fbx extension.
  echo Single actor; 12 to 600 frames. Existing FBX files are not overwritten.
  pause
  popd
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo Python environment is missing. Run SetupStandalone.bat first.
  pause
  popd
  exit /b 1
)
".venv\Scripts\python.exe" -u -m m2a.drop_video %*
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" echo Failed. See the error above; partial results remain in runs\drop.
pause
popd
exit /b %RESULT%
