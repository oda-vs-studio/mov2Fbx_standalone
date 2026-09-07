@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Run SetupMovie2Anim.bat first.
  pause
  exit /b 1
)
start "Movie2Anim Standalone" ".venv\Scripts\pythonw.exe" -m m2a gui
