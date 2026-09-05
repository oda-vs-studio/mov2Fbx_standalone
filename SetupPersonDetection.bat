@echo off
setlocal
pushd "%~dp0"
".venv\Scripts\python.exe" -m tools.setup_detection
set "RESULT=%ERRORLEVEL%"
pause
popd
exit /b %RESULT%
