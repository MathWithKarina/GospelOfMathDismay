"""Extensible adapter registry. Only already-installed Python entry points are loaded."""
from __future__ import annotations
import logging
from importlib.metadata import entry_points
from pathlib import Path
from .base import TTSAdapter
from .piper import PiperCLIAdapter

log=logging.getLogger(__name__)

class TTSRegistry:
    ENTRY_POINT_GROUP="gomd.tts_adapters"
    def __init__(self, include_builtin: bool=True):
        self._adapters:dict[str,TTSAdapter]={}
        if include_builtin: self.register(PiperCLIAdapter())
    def register(self, adapter:TTSAdapter, replace:bool=False):
        if not isinstance(adapter,TTSAdapter): raise TypeError("Registered engine must implement TTSAdapter")
        if adapter.id in self._adapters and not replace: raise ValueError(f"TTS engine already registered: {adapter.id}")
        self._adapters[adapter.id]=adapter
    def get(self,engine_id:str)->TTSAdapter:
        try: return self._adapters[engine_id]
        except KeyError as exc: raise KeyError(f"TTS engine is not registered: {engine_id}") from exc
    def adapters(self)->list[TTSAdapter]: return list(self._adapters.values())
    @classmethod
    def discover(cls, include_builtin:bool=True)->"TTSRegistry":
        registry=cls(include_builtin=include_builtin)
        try:
            available=entry_points()
            selected=available.select(group=cls.ENTRY_POINT_GROUP) if hasattr(available,"select") else available.get(cls.ENTRY_POINT_GROUP,[])
        except Exception:
            log.exception("Could not inspect installed TTS adapter entry points"); return registry
        for ep in selected:
            try:
                loaded=ep.load(); adapter=loaded() if callable(loaded) else loaded
                registry.register(adapter)
                log.info("Registered TTS adapter plugin: %s (%s)",adapter.name,adapter.id)
            except Exception:
                log.exception("Skipping invalid TTS adapter entry point %s",getattr(ep,"name","unknown"))
        return registry
