@echo off
setlocal
chcp 65001 >nul
pushd "%~dp0"
set "PYTHONUTF8=1"
if "%~1"=="" (
  echo Drop one or more videos onto this BAT.
  echo Creates a new VIDEO_Movie2Anim_DATE_ID folder beside each video.
  echo Animates the primary actor. Add --actor-mode all to include other actors.
  echo Exports all accepted segments. Failed intervals are recorded and skipped.
  goto failed
)
if not exist ".venv\Scripts\python.exe" (
  echo Run SetupMovie2Anim.bat first.
  goto failed
)
if not exist ".venv-camera\Scripts\python.exe" (
  echo Run SetupMovie2Anim.bat first.
  goto failed
)
".venv\Scripts\python.exe" -u -m m2a.drop_video --moving-camera --output-folder --actor-mode primary %*
set "RESULT=%ERRORLEVEL%"
goto finish
:failed
set "RESULT=1"
:finish
if not "%RESULT%"=="0" echo Failed. Details and intermediate work remain in the result folder.
if not defined M2A_NO_PAUSE pause
popd
exit /b %RESULT%
