from __future__ import annotations
import logging
from logging.handlers import RotatingFileHandler
from .paths import log_dir

def configure_logging() -> None:
    folder = log_dir()
    folder.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    if root.handlers:
        return
    root.setLevel(logging.INFO)
    handler = RotatingFileHandler(folder / "gomd.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)
    root.addHandler(logging.StreamHandler())
