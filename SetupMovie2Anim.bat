@echo off
setlocal
pushd "%~dp0"
set "PYTHONUTF8=1"
if defined M2A_PYTHON goto custom
py -3.13 -c "import sys" >nul 2>&1
if not errorlevel 1 (
  py -3.13 -m tools.setup_all %*
  goto finish
)
python -c "import sys" >nul 2>&1
if errorlevel 1 (
  echo Python 3.13 x64 is required. Install it from https://www.python.org/downloads/windows/
  set "RESULT=1"
  goto done
)
python -m tools.setup_all %*
goto finish
:custom
"%M2A_PYTHON%" -m tools.setup_all %*
:finish
set "RESULT=%ERRORLEVEL%"
:done
if not "%RESULT%"=="0" echo Setup failed. Existing models and runs were preserved. See the error above.
if not defined M2A_SETUP_NO_PAUSE pause
popd
exit /b %RESULT%
