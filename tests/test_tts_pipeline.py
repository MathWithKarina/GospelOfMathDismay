import json, sys, wave
from pathlib import Path
import pytest
from gomd.tts.piper import PiperCLIAdapter
from gomd.tts.base import TTSAdapter, TTSCapabilities, TTSRequest, TTSResult
from gomd.core.project import Project
from gomd.scenes.pipeline import synthesize_project_scenes, assemble_project_audio
from gomd.audio.wav_tools import inspect_wav

class FakeTTS(TTSAdapter):
    id="fake-test"; name="Fake test TTS"; capabilities=TTSCapabilities(supports_speed=True)
    def is_available(self): return True
    def synthesize(self, request, cancel_event=None, progress=None):
        if cancel_event is not None and cancel_event.is_set(): raise InterruptedError("cancelled")
        request.output_path.parent.mkdir(parents=True,exist_ok=True)
        with wave.open(str(request.output_path),"wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000); w.writeframes(b"\x10\x00"*800)
        return TTSResult(request.output_path,0.1,self.id,request.model_path)

def fake_model(tmp_path):
    model=tmp_path/"fake.onnx"; model.write_bytes(b"test-model")
    Path(str(model)+".json").write_text(json.dumps({"audio":{"sample_rate":8000}}),encoding="utf-8")
    return model

def test_piper_missing_model_and_sidecar_are_reported(tmp_path):
    adapter=PiperCLIAdapter(sys.executable)
    missing=tmp_path/"missing.onnx"
    with pytest.raises(FileNotFoundError,match="model not found"):
        adapter.synthesize(TTSRequest("hello",tmp_path/"a.wav",missing))
    model=fake_model(tmp_path)
    Path(str(model)+".json").unlink()
    with pytest.raises(FileNotFoundError,match="sidecar"):
        adapter.synthesize(TTSRequest("hello",tmp_path/"a.wav",model))

def test_piper_refuses_to_overwrite_existing_output(tmp_path):
    model=fake_model(tmp_path); out=tmp_path/"keep.wav"; out.write_bytes(b"do not replace")
    adapter=PiperCLIAdapter(sys.executable)
    with pytest.raises(FileExistsError): adapter.synthesize(TTSRequest("hello",out,model))
    assert out.read_bytes()==b"do not replace"

def test_batch_synthesis_then_assemble_final_audio(tmp_path):
    model=fake_model(tmp_path)
    project=Project.create(tmp_path/"lesson","Lesson")
    first=project.scenes[0]; first.text="Hello, world."; first.normalized_text="Hello, world."
    second=project.add_scene("Second"); second.text="Second scene."; second.normalized_text="Second scene."
    generated=synthesize_project_scenes(project,FakeTTS(),model,speed=1.0)
    assert len(generated)==2 and all(p.is_file() for p in generated)
    assert all(scene.settings.get("pitch")==0.0 for scene in project.scenes)
    final=assemble_project_audio(project,pause_ms=100)
    info=inspect_wav(final,False)
    assert final.name=="final.wav" and info.duration_seconds>=0.3
    with pytest.raises(FileExistsError): assemble_project_audio(project,pause_ms=0)
    final2=assemble_project_audio(project,pause_ms=0,overwrite=True)
    assert final2.is_file()

def test_batch_respects_cancel_flag(tmp_path):
    from threading import Event
    model=fake_model(tmp_path); project=Project.create(tmp_path/"lesson","Lesson")
    project.scenes[0].text="Hello."
    event=Event(); event.set()
    with pytest.raises(InterruptedError): synthesize_project_scenes(project,FakeTTS(),model,cancel_event=event)


def test_punctuation_pauses_are_inserted_into_synthesized_wav(tmp_path):
    from gomd.audio.processor import PauseSettings, synthesize_with_pauses
    model=fake_model(tmp_path); output=tmp_path/"punctuation.wav"
    request=TTSRequest(text="Hello, world.",output_path=output,model_path=model)
    synthesize_with_pauses(FakeTTS(),request,PauseSettings(comma_ms=100,period_ms=500))
    info=inspect_wav(output,False)
    # Two 100 ms test utterances plus a 100 ms comma pause; no terminal pause is appended.
    assert abs(info.duration_seconds-0.3)<0.02
