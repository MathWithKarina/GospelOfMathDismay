@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo Python Launcher was not found. Install 64-bit Python 3.11, 3.12 or 3.13 from python.org first.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  py -3.13 -m venv .venv 2>nul
  if errorlevel 1 py -3.12 -m venv .venv 2>nul
  if errorlevel 1 py -3.11 -m venv .venv
  if errorlevel 1 (
    echo Could not create a virtual environment. Check that Python 3.11, 3.12 or 3.13 is installed.
    pause
    exit /b 1
  )
)
call ".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :failed
call ".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :failed
call ".venv\Scripts\python.exe" -m pip install -e .
if errorlevel 1 goto :failed
echo.
echo Installation completed. Run run_windows.bat to start GoMD.
pause
exit /b 0
:failed
echo Installation failed. Check the error above and your network connection.
pause
exit /b 1
