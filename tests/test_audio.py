import wave
from pathlib import Path
from gomd.audio.wav_tools import inspect_wav, concatenate_wavs
from gomd.audio.processor import PauseSettings
from gomd.audio.processor import _text_chunks

def make_wav(path,rate=8000,channels=1,width=2,frames=800,value=1000):
    path=Path(path)
    with wave.open(str(path),"wb") as w:
        w.setnchannels(channels); w.setsampwidth(width); w.setframerate(rate)
        if width==2: data=(value.to_bytes(2,"little",signed=True))*frames*channels
        elif width==1: data=bytes([value])*frames*channels
        else: raise ValueError
        w.writeframes(data)
    return path

def test_inspect_wav_metadata_and_levels(tmp_path):
    path=make_wav(tmp_path/"tone.wav",frames=400)
    info=inspect_wav(path)
    assert info.sample_rate==8000 and info.channels==1
    assert info.duration_seconds==0.05
    assert info.peak>0 and info.rms>0

def test_concatenate_with_pause(tmp_path):
    a=make_wav(tmp_path/"a.wav",frames=800)
    b=make_wav(tmp_path/"b.wav",frames=800)
    output=concatenate_wavs([a,b],tmp_path/"final.wav",pause_ms=100)
    info=inspect_wav(output,False)
    assert abs(info.duration_seconds-0.3)<0.01

def test_text_chunks_respect_punctuation():
    chunks=_text_chunks("Hello, world. Next!\nDone.")
    assert len(chunks)>=3
    assert chunks[0].endswith(",")
    assert PauseSettings().duration_after(".")>PauseSettings().duration_after(",")
    paragraphs=_text_chunks("First sentence.\n\nSecond paragraph.")
    assert paragraphs[0].endswith("\n")


def test_spectrogram_returns_finite_dimensions(tmp_path):
    import numpy as np
    from gomd.audio.analyzer import spectrogram
    path=tmp_path/"tone.wav"
    rate=8000; samples=(np.sin(2*np.pi*440*np.arange(rate)/rate)*10000).astype("<i2")
    with wave.open(str(path),"wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(samples.tobytes())
    info,times,freqs,db=spectrogram(path,n_fft=256,hop_length=64)
    assert info.sample_rate==rate and len(times)>1 and len(freqs)==129
    assert db.shape==(len(freqs),len(times)) and np.isfinite(db).all()


def test_ffmpeg_speed_and_pitch_are_valid_when_available(tmp_path):
    import shutil
    import pytest
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg is optional and not installed")
    import numpy as np
    from gomd.audio.processor import AudioProcessor
    rate=8000; samples=(np.sin(2*np.pi*220*np.arange(rate//2)/rate)*12000).astype("<i2")
    source=tmp_path/"source.wav"
    with wave.open(str(source),"wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(samples.tobytes())
    processor=AudioProcessor()
    fast=processor.change_speed(source,tmp_path/"fast.wav",2.0)
    pitched=processor.change_pitch(source,tmp_path/"pitched.wav",3.0)
    assert 0.24 <= inspect_wav(fast,False).duration_seconds <= 0.26
    assert inspect_wav(pitched,False).sample_rate==rate
    assert 0.4 <= inspect_wav(pitched,False).duration_seconds < 0.5
    import pytest
    with pytest.raises(FileExistsError): processor.change_speed(source,fast,1.25)
    with pytest.raises(ValueError): processor.change_pitch(source,source,1.0)
