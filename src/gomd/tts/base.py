from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

@dataclass(frozen=True)
class TTSCapabilities:
    languages: tuple[str,...] = ()
    supports_speed: bool = False
    supports_pitch: bool = False
    supports_emotion: bool = False
    supports_cancellation: bool = False
    notes: str = ""

@dataclass
class TTSRequest:
    text: str
    output_path: Path
    model_path: Path
    speed: float = 1.0
    speaker_id: int | None = None
    extra_options: dict = field(default_factory=dict)

@dataclass
class TTSResult:
    output_path: Path
    duration_seconds: float
    engine_id: str
    model_path: Path
    stdout: str = ""
    metadata: dict = field(default_factory=dict)

class TTSAdapter(ABC):
    id="base"; name="Abstract TTS engine"
    capabilities=TTSCapabilities()
    @abstractmethod
    def is_available(self) -> bool: ...
    @abstractmethod
    def synthesize(self, request: TTSRequest, cancel_event=None, progress: Callable[[str],None] | None=None) -> TTSResult: ...
    def validate_model(self, model_path: Path) -> tuple[bool,str]:
        path=Path(model_path).expanduser()
        return (True,"Model file exists.") if path.is_file() else (False,f"Model file was not found: {path}")
    def discover_models(self, directory: Path) -> list[Path]:
        """Plugins may override this to list compatible local models; default is intentionally empty."""
        return []
    def voice_list(self) -> list[dict]:
        """Return optional engine-specific voice/model metadata. Implementations should not guess licenses."""
        return []
    def license_info(self) -> str: return "Review the selected engine/model documentation before redistribution or commercial use."
