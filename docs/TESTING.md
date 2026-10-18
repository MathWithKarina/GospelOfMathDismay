# Testing notes

Run `python -m pytest -q` from the project root, or use `test_windows.bat` on Windows. The core test suite is intentionally offline and does not need PySide6 or a voice model. Real engine tests need a separately installed compatible Piper executable and a licensed model pair.

The release environment used for this first build is Linux with Python 3.13, NumPy, Matplotlib, FFmpeg and pytest available. PySide6 was not installed there. Consequently the Qt window was syntax-compiled but could not be launched in this environment; a Windows GUI smoke test and Windows `.exe` build are still needed.
