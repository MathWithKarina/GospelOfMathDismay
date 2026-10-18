from __future__ import annotations
import importlib.util, os, platform, shutil, sys
from pathlib import Path
from .. import __version__
from ..core.paths import config_dir, data_dir, log_dir

def collect_diagnostics(piper_path: str="piper", model_path: str="") -> str:
    packages={name:bool(importlib.util.find_spec(name)) for name in ("PySide6","numpy","matplotlib","pytest")}
    lines=[f"Application: Gospel Of Math Dismay {__version__}",f"Python: {sys.version.split()[0]}",f"Platform: {platform.platform()}",
        f"Executable: {sys.executable}",f"Piper available: {bool(shutil.which(piper_path) or (Path(piper_path).is_file() if piper_path else False))}",
        f"Selected model configured: {bool(model_path)}",f"Selected model file exists: {Path(model_path).is_file() if model_path else False}",
        "Dependencies: "+", ".join(f"{k}={'yes' if v else 'no'}" for k,v in packages.items()),
        f"Config directory: {config_dir()}",f"Data directory: {data_dir()}",f"Logs directory: {log_dir()}",
        "Privacy: user text, filenames and credentials are not included in this report."]
    return "\n".join(lines)
def open_log_directory():
    path=log_dir(); path.mkdir(parents=True,exist_ok=True); return path
