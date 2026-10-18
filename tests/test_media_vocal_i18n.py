import pytest
from gomd.media.library import MediaLibrary
from gomd.vocal.music import Note, VocalProject, render_preview_wav
from gomd.audio.wav_tools import inspect_wav
from gomd.i18n.translations import translate, SUPPORTED_LANGUAGES

def test_media_scanning_and_delete_confirmation(tmp_path):
    import wave
    path=tmp_path/"record.wav"
    with wave.open(str(path),"wb") as w: w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000); w.writeframes(b"\0\0"*100)
    lib=MediaLibrary(); assert lib.scan(tmp_path)[0].name=="record.wav"
    with pytest.raises(PermissionError): lib.delete(path)
    lib.delete(path,confirmed=True); assert not path.exists()

def test_vocal_project_roundtrip_and_preview(tmp_path):
    project=VocalProject(bpm=120,notes=[Note(0,1,60,"la"),Note(1,1,64,"mi")])
    json_path=tmp_path/"vocal.json"; project.save(json_path)
    reopened=VocalProject.load(json_path); assert len(reopened.notes)==2
    wav=render_preview_wav(reopened,tmp_path/"preview.wav")
    assert inspect_wav(wav,False).duration_seconds>0.9

def test_localization_basics():
    assert set(SUPPORTED_LANGUAGES)=={"ru","en-GB"}
    assert translate("nav.studio","ru")=="Студия"
    assert translate("nav.studio","en-GB")=="Studio"
