@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo First run install_windows.bat to install dependencies.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m gomd
if errorlevel 1 (
  echo GoMD did not start. Run diagnose_windows.bat and check the application log.
  pause
)
