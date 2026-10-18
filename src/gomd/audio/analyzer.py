from __future__ import annotations
import csv, struct, wave
from pathlib import Path
import numpy as np
from .wav_tools import inspect_wav

def load_audio(path: Path):
    info=inspect_wav(path,False)
    with wave.open(str(Path(path)),"rb") as w: raw=w.readframes(w.getnframes())
    width=info.sample_width
    if width==1: samples=(np.frombuffer(raw,dtype=np.uint8).astype(np.float32)-128)/128
    elif width==2: samples=np.frombuffer(raw,dtype="<i2").astype(np.float32)/32768
    elif width==4: samples=np.frombuffer(raw,dtype="<i4").astype(np.float32)/2147483648
    elif width==3:
        values=np.frombuffer(raw,dtype=np.uint8).reshape(-1,3)
        ints=values[:,0].astype(np.int32)|(values[:,1].astype(np.int32)<<8)|(values[:,2].astype(np.int32)<<16)
        ints=np.where(ints & 0x800000,ints-0x1000000,ints)
        samples=ints.astype(np.float32)/8388608
    else: raise ValueError("Unsupported PCM sample width")
    if info.channels>1: samples=samples.reshape(-1,info.channels).mean(axis=1)
    times=np.arange(len(samples),dtype=np.float64)/info.sample_rate
    return info,times,samples

def spectrum(path: Path):
    info,times,samples=load_audio(path)
    if len(samples)==0: raise ValueError("Audio is empty")
    window=np.hanning(len(samples)); spec=np.abs(np.fft.rfft(samples*window))
    freqs=np.fft.rfftfreq(len(samples),1/info.sample_rate)
    return info,freqs,20*np.log10(np.maximum(spec/spec.max(initial=1),1e-12))

def export_waveform_csv(path: Path, output: Path, stride: int=1):
    info,times,samples=load_audio(path); stride=max(1,int(stride)); output=Path(output).resolve(); output.parent.mkdir(parents=True,exist_ok=True)
    with output.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.writer(f); w.writerow(["time_seconds","amplitude"])
        w.writerows((f"{times[i]:.8f}",f"{samples[i]:.8f}") for i in range(0,len(samples),stride))
    return output


def spectrogram(path: Path, n_fft: int = 1024, hop_length: int = 256):
    """Return (WAV info, frame-centre times, frequencies, relative magnitude dB)."""
    info,times,samples=load_audio(path)
    if not len(samples): raise ValueError("Audio is empty")
    n_fft=max(32,int(n_fft)); hop_length=max(1,int(hop_length))
    if len(samples)<n_fft:
        samples=np.pad(samples,(0,n_fft-len(samples)))
    starts=np.arange(0,max(1,len(samples)-n_fft+1),hop_length,dtype=int)
    if starts.size==0: starts=np.asarray([0],dtype=int)
    window=np.hanning(n_fft).astype(np.float32)
    frames=np.stack([samples[start:start+n_fft] for start in starts])
    magnitude=np.abs(np.fft.rfft(frames*window[None,:],axis=1)).T
    peak=float(magnitude.max()) if magnitude.size else 0.0
    db=20*np.log10(np.maximum(magnitude/(peak if peak>0 else 1.0),1e-12))
    frame_times=(starts+n_fft/2)/info.sample_rate
    frequencies=np.fft.rfftfreq(n_fft,1/info.sample_rate)
    return info,frame_times,frequencies,db
