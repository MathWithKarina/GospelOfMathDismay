"""Predictable user-space paths; never writes to a drive root or installation folder."""
from __future__ import annotations
import os
import sys
from pathlib import Path

APP_DIR_NAME = "GospelOfMathDismay"

def _user_home() -> Path:
    return Path.home()

def config_dir() -> Path:
    if os.name == "nt":
        base = os.environ.get("APPDATA")
        return Path(base) / APP_DIR_NAME if base else _user_home() / "AppData" / "Roaming" / APP_DIR_NAME
    base = os.environ.get("XDG_CONFIG_HOME")
    return Path(base) / APP_DIR_NAME if base else _user_home() / ".config" / APP_DIR_NAME

def data_dir() -> Path:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        return Path(base) / APP_DIR_NAME if base else _user_home() / "AppData" / "Local" / APP_DIR_NAME
    base = os.environ.get("XDG_DATA_HOME")
    return Path(base) / APP_DIR_NAME if base else _user_home() / ".local" / "share" / APP_DIR_NAME

def log_dir() -> Path:
    if os.name == "nt":
        return data_dir() / "logs"
    base = os.environ.get("XDG_STATE_HOME")
    return (Path(base) / APP_DIR_NAME / "logs") if base else (_user_home() / ".local" / "state" / APP_DIR_NAME / "logs")

def ensure_user_dirs() -> None:
    """Create only app-owned subfolders in the normal user profile."""
    for path in (config_dir(), data_dir(), log_dir(), data_dir() / "models", data_dir() / "cache"):
        path.mkdir(parents=True, exist_ok=True)

def default_model_dir() -> Path:
    return data_dir() / "models"

def default_projects_hint() -> Path:
    """An informational suggestion only; callers must ask before creating a project."""
    docs = _user_home() / "Documents"
    return docs / APP_DIR_NAME / "Projects"
