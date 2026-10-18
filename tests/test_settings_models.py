import json
from pathlib import Path
from gomd.core.settings import AppSettings
from gomd.models.catalog import VoiceModel, ModelCatalogClient

def test_settings_are_saved_atomically_and_values_clamped(tmp_path):
    p=tmp_path/"settings.json"
    s=AppSettings(language="en-GB",speech_rate=1.25,comma_pause_ms=130)
    s.save(p)
    loaded=AppSettings.load(p)
    assert loaded.language=="en-GB" and loaded.speech_rate==1.25 and loaded.comma_pause_ms==130
    p.write_text('{not-json',encoding='utf-8')
    assert AppSettings.load(p).language=="ru"

def test_voice_model_urls_are_https_and_metadata_clear():
    model=VoiceModel("en/en_GB/alba/medium/en_GB-alba-medium.onnx","en_GB-alba-medium","en_GB","medium",
        "https://huggingface.co/example/model.onnx","https://huggingface.co/example/model.onnx.json",
        "https://huggingface.co/example/MODEL_CARD","https://huggingface.co/example")
    assert model.model_url.startswith("https://")
    assert "MODEL_CARD" in model.license_url
    assert "unknown" in model.size_label
    assert ModelCatalogClient().user_agent.startswith("GospelOfMathDismay")


def test_tts_registry_has_piper_and_rejects_duplicate_ids():
    import pytest
    from gomd.tts.registry import TTSRegistry
    from gomd.tts.piper import PiperCLIAdapter
    registry=TTSRegistry()
    assert registry.get("piper-cli").name.startswith("Piper")
    with pytest.raises(ValueError,match="already registered"):
        registry.register(PiperCLIAdapter())
