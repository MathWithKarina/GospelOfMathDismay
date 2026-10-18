from __future__ import annotations
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from .paths import config_dir

@dataclass
class AppSettings:
    language: str = "ru"
    tts_text_language: str = "ru"
    tts_engine: str = "piper-cli"
    piper_executable: str = "piper"
    model_directory: str = ""
    selected_model: str = ""
    output_directory: str = ""
    speech_rate: float = 1.0
    pitch_semitones: float = 0.0
    comma_pause_ms: int = 120
    period_pause_ms: int = 320
    semicolon_pause_ms: int = 180
    colon_pause_ms: int = 180
    ellipsis_pause_ms: int = 420
    question_pause_ms: int = 250
    exclamation_pause_ms: int = 250
    paragraph_pause_ms: int = 500
    scene_pause_ms: int = 400
    graph_x_min: float = -10.0
    graph_x_max: float = 10.0
    graph_y_min: float = -10.0
    graph_y_max: float = 10.0
    autosave_seconds: int = 60
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path | None = None) -> "AppSettings":
        target = path or config_dir() / "settings.json"
        try:
            raw = json.loads(target.read_text(encoding="utf-8"))
            known = {k: v for k, v in raw.items() if k in cls.__dataclass_fields__}
            result = cls(**known)
            result.speech_rate = min(2.0, max(0.5, float(result.speech_rate)))
            result.pitch_semitones = min(8.0, max(-8.0, float(result.pitch_semitones)))
            result.language = result.language if result.language in {"ru", "en-GB"} else "ru"
            result.tts_text_language = result.tts_text_language if result.tts_text_language in {"ru", "en-GB"} else "ru"
            return result
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return cls()

    def save(self, path: Path | None = None) -> None:
        target = path or config_dir() / "settings.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(target)
