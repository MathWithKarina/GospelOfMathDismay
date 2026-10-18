from __future__ import annotations
import logging, sys
from ..core.logging_setup import configure_logging
from ..core.paths import ensure_user_dirs, config_dir
from ..core.settings import AppSettings
from ..i18n.translations import detect_windows_language
from .. import APP_NAME

def main() -> int:
    ensure_user_dirs(); configure_logging(); log=logging.getLogger(__name__)
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
    except ImportError:
        print(f"{APP_NAME} needs its desktop dependencies.\nRun install_windows.bat on Windows or: python -m pip install -r requirements.txt",file=sys.stderr)
        return 2
    first_run=not (config_dir()/"settings.json").exists()
    settings=AppSettings.load()
    if first_run or settings.language not in ("ru","en-GB"):
        settings.language=detect_windows_language()
    app=QApplication(sys.argv); app.setApplicationName(APP_NAME); app.setOrganizationName("Karina x ChatGPT")
    try:
        from ..ui.main_window import MainWindow
        window=MainWindow(settings); window.show()
        return app.exec()
    except Exception as exc:
        log.exception("Application could not start")
        QMessageBox.critical(None,"Gospel Of Math Dismay",f"The application could not start.\n{exc}\n\nDiagnostic log: see the user log folder.")
        return 1
