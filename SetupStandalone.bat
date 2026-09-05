@echo off
setlocal
cd /d "%~dp0"
if not defined UE_ROOT set "UE_ROOT=D:\UE\UE_5.8"
if not exist .venv\Scripts\python.exe python -m venv .venv
if errorlevel 1 goto failed
set "REQUIREMENTS=requirements.txt"
if exist requirements.lock.txt set "REQUIREMENTS=requirements.lock.txt"
.venv\Scripts\python.exe -m pip install -r "%REQUIREMENTS%"
if errorlevel 1 goto failed
.venv\Scripts\python.exe tools\extract_models.py --engine "%UE_ROOT%"
if errorlevel 1 goto failed
.venv\Scripts\python.exe tools\extract_skeleton.py --engine "%UE_ROOT%"
if errorlevel 1 goto failed
call tools\build_fbx.bat
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m unittest discover -s tests -v
if errorlevel 1 goto failed
call tools\build_skeleton.bat
if errorlevel 1 goto failed
call tools\build_retarget.bat
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m unittest discover -s tests -v
if errorlevel 1 goto failed
echo Setup complete. LaunchStandalone.bat opens the tool.
pause
exit /b 0
:failed
echo Setup failed. See the error above.
pause
exit /b 1
