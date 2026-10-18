from __future__ import annotations
from dataclasses import dataclass
import math, shutil, struct, subprocess, tempfile, wave
from pathlib import Path

@dataclass
class WavInfo:
    path: Path
    sample_rate: int
    channels: int
    sample_width: int
    frames: int
    duration_seconds: float
    peak: float
    rms: float
    compression: str

def _decode_pcm(data: bytes, width: int):
    if width==1: return [(b-128)/128.0 for b in data]
    if width==2:
        count=len(data)//2; return [x/32768.0 for x in struct.unpack("<"+"h"*count,data[:count*2])]
    if width==3:
        values=[]
        for i in range(0,len(data)-2,3):
            n=data[i] | (data[i+1]<<8) | (data[i+2]<<16)
            if n & 0x800000: n-=1<<24
            values.append(n/8388608.0)
        return values
    if width==4:
        count=len(data)//4; return [x/2147483648.0 for x in struct.unpack("<"+"i"*count,data[:count*4])]
    raise ValueError(f"Unsupported PCM sample width: {width} bytes")

def inspect_wav(path: Path, calculate_levels: bool=True) -> WavInfo:
    path=Path(path).expanduser().resolve()
    if not path.is_file(): raise FileNotFoundError(path)
    try:
        with wave.open(str(path),"rb") as wav:
            channels,rate,width,frames,compression=wav.getnchannels(),wav.getframerate(),wav.getsampwidth(),wav.getnframes(),wav.getcomptype()
            if compression!="NONE": raise ValueError(f"Unsupported WAV compression: {compression}")
            if channels<1 or rate<1 or frames<0: raise ValueError("Invalid WAV header")
            duration=frames/rate if rate else 0.0
            peak=rms=0.0
            if calculate_levels and frames:
                vals=_decode_pcm(wav.readframes(frames),width)
                peak=max((abs(v) for v in vals),default=0.0)
                rms=math.sqrt(sum(v*v for v in vals)/len(vals)) if vals else 0.0
            return WavInfo(path,rate,channels,width,frames,duration,peak,rms,compression)
    except (wave.Error,EOFError) as exc:
        raise ValueError(f"Not a readable uncompressed PCM WAV file: {exc}") from exc

def _write_silence(wav: wave.Wave_write, milliseconds: int, rate:int, channels:int, width:int):
    frames=max(0,int(rate*milliseconds/1000))
    # 8-bit PCM silence is 0x80; signed widths are zero.
    byte=bytes([128]) if width==1 else bytes([0])
    wav.writeframesraw(byte*(frames*channels*width))

def concatenate_wavs(inputs: list[Path], output: Path, pause_ms: int=0, target_rate: int|None=None) -> Path:
    if not inputs: raise ValueError("Select at least one WAV file")
    output=Path(output).expanduser().resolve(); output.parent.mkdir(parents=True,exist_ok=True)
    files=[Path(p).expanduser().resolve() for p in inputs]
    infos=[inspect_wav(p,False) for p in files]
    rate=target_rate or infos[0].sample_rate
    channels=infos[0].channels
    width=infos[0].sample_width
    # Normalize genuinely incompatible files through FFmpeg rather than byte-concatenating unlike PCM.
    needs_ffmpeg=any((i.sample_rate,i.channels,i.sample_width)!=(rate,channels,width) for i in infos)
    temp_dir=None
    if needs_ffmpeg:
        ffmpeg=shutil.which("ffmpeg")
        if not ffmpeg: raise RuntimeError("The WAV files use different formats; install FFmpeg to normalize them before joining.")
        temp_dir=tempfile.TemporaryDirectory(prefix="gomd_audio_")
        converted=[]
        for idx,path in enumerate(files):
            dest=Path(temp_dir.name)/f"{idx:04d}.wav"
            cmd=[ffmpeg,"-nostdin","-hide_banner","-loglevel","error","-y","-i",str(path),"-ar",str(rate),"-ac",str(channels),"-c:a","pcm_s16le",str(dest)]
            p=subprocess.run(cmd,capture_output=True,text=True,timeout=180)
            if p.returncode: temp_dir.cleanup(); raise RuntimeError("FFmpeg could not normalize audio: "+p.stderr[-1000:])
            converted.append(dest)
        files=converted; width=2
    tmp=output.with_name(output.stem+".writing.wav")
    try:
        with wave.open(str(tmp),"wb") as dest:
            dest.setnchannels(channels); dest.setsampwidth(width); dest.setframerate(rate)
            for idx,path in enumerate(files):
                with wave.open(str(path),"rb") as src:
                    if src.getnchannels()!=channels or src.getsampwidth()!=width or src.getframerate()!=rate: raise ValueError("Internal format normalization mismatch")
                    while True:
                        block=src.readframes(65536)
                        if not block: break
                        dest.writeframesraw(block)
                if pause_ms and idx<len(files)-1: _write_silence(dest,pause_ms,rate,channels,width)
        inspect_wav(tmp,False)
        tmp.replace(output)
    finally:
        tmp.unlink(missing_ok=True)
        if temp_dir: temp_dir.cleanup()
    return output
