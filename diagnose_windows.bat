@echo off
setlocal
cd /d "%~dp0"
echo === Windows ===
ver
echo === Python ===
where py 2>nul
py -0p 2>nul
echo === FFmpeg ===
where ffmpeg 2>nul
echo === GoMD runtime diagnostics ===
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "from gomd.help.diagnostics import collect_diagnostics; print(collect_diagnostics())"
) else (
  echo Project virtual environment not found. Run install_windows.bat first.
)
echo === Piper ===
where piper 2>nul
echo Diagnostic listing completed. See %%LOCALAPPDATA%%\GospelOfMathDismay\logs for app logs.
pause
