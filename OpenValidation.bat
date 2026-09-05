@echo off
if exist "%~dp0runs\user_validation\index.html" (
  start "" "%~dp0runs\user_validation\index.html"
) else (
  echo No validation results. Run tools\validate_user_videos.py and tools\report_validation.py first.
  pause
)
