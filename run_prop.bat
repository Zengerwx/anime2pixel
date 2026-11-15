@echo off
REM usage: drag an image onto this bat = convert one; double-click = batch convert in\ folder
set "PY=D:\ComfyUI_src\.venv\Scripts\python.exe"
set "SCRIPT=%~dp0run_demo.py"
if not exist "%PY%" (
  echo [!] ComfyUI python not found: %PY%
  pause
  exit /b 1
)
"%PY%" "%SCRIPT%" %1
pause
