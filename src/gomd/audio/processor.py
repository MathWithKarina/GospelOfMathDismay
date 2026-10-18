from __future__ import annotations
import math, re, shutil, subprocess, tempfile, threading, wave, uuid
from dataclasses import dataclass
from pathlib import Path
from .wav_tools import concatenate_wavs, inspect_wav
from ..tts.base import TTSAdapter, TTSRequest

@dataclass
class PauseSettings:
    comma_ms: int=120
    period_ms: int=320
    semicolon_ms: int=180
    colon_ms: int=180
    ellipsis_ms: int=420
    question_ms: int=250
    exclamation_ms: int=250
    paragraph_ms: int=500
    def duration_after(self, punctuation: str) -> int:
        return {",":self.comma_ms,".":self.period_ms,";":self.semicolon_ms,":":self.colon_ms,
                "…":self.ellipsis_ms,"?":self.question_ms,"!":self.exclamation_ms,"\n":self.paragraph_ms}.get(punctuation,0)

def _text_chunks(text: str):
    # Preserve paragraph breaks as a marker on the preceding chunk so their pause
    # survives the later trim applied before text is sent to the speech engine.
    text=text.replace("\r\n","\n").replace("\r","\n")
    pattern=re.compile(r"(.+?(?:…|\.\.\.|[,.!?;:]|\n+|$))",re.DOTALL)
    raw=[m.group(1) for m in pattern.finditer(text)]
    chunks=[]
    for piece in raw:
        if piece.startswith("\n") and chunks:
            chunks[-1]=chunks[-1].rstrip("\n")+"\n"
            piece=piece.lstrip("\n")
        if not piece.strip():
            if chunks: chunks[-1]=chunks[-1].rstrip("\n")+"\n"
            continue
        paragraph_end=piece.endswith("\n")
        clean=piece.strip()
        chunks.append(clean+("\n" if paragraph_end else ""))
    return chunks

def synthesize_with_pauses(adapter: TTSAdapter, request: TTSRequest, pauses: PauseSettings,
                           cancel_event=None, progress=None) -> Path:
    chunks=_text_chunks(request.text)
    if len(chunks)<=1:
        adapter.synthesize(request,cancel_event,progress)
        return request.output_path
    temp= tempfile.TemporaryDirectory(prefix="gomd_segments_")
    generated=[]; silence_values=[]
    try:
        for idx,chunk in enumerate(chunks):
            if cancel_event is not None and cancel_event.is_set(): raise InterruptedError("Synthesis cancelled.")
            target=Path(temp.name)/f"segment_{idx:04d}.wav"
            speech_text=chunk.rstrip("\n").strip()
            if not speech_text: continue
            adapter.synthesize(TTSRequest(text=speech_text,output_path=target,model_path=request.model_path,speed=request.speed,
                                          speaker_id=request.speaker_id,extra_options=request.extra_options),cancel_event,progress)
            generated.append(target)
            punct="\n" if chunk.endswith("\n") else ("…" if chunk.endswith(("…","...")) else chunk[-1:])
            silence_values.append(pauses.duration_after(punct))
        if not generated: raise ValueError("No speech text remained after splitting the input.")
        # Insert silence as actual PCM WAV pieces so each punctuation class gets its own duration.
        with wave.open(str(generated[0]),"rb") as sample:
            rate,channels,width=sample.getframerate(),sample.getnchannels(),sample.getsampwidth()
        pieces=[]
        for idx,path in enumerate(generated):
            pieces.append(path)
            pause=silence_values[idx]
            if idx<len(generated)-1 and pause>0:
                silence=Path(temp.name)/f"silence_{idx:04d}.wav"
                with wave.open(str(silence),"wb") as w:
                    w.setnchannels(channels); w.setsampwidth(width); w.setframerate(rate)
                    frames=int(rate*pause/1000); value=bytes([128]) if width==1 else bytes([0])
                    w.writeframes(value*frames*channels*width)
                pieces.append(silence)
        concatenate_wavs(pieces,request.output_path,pause_ms=0)
        inspect_wav(request.output_path,False)
        return request.output_path
    finally:
        temp.cleanup()

class AudioProcessor:
    def __init__(self, ffmpeg: str="ffmpeg"): self.ffmpeg=ffmpeg
    def _binary(self):
        found=shutil.which(self.ffmpeg)
        if not found: raise FileNotFoundError("FFmpeg was not found. Set its executable in Settings or install FFmpeg.")
        return found
    def change_speed(self, source:Path, output:Path, speed:float) -> Path:
        speed=float(speed)
        if not 0.5<=speed<=2.0: raise ValueError("Speed must be between 0.5× and 2.0×")
        source=Path(source).expanduser().resolve(); output=Path(output).expanduser().resolve()
        if source==output: raise ValueError("Choose a new output path; the source audio will not be overwritten in place.")
        if output.exists(): raise FileExistsError(f"Refusing to overwrite an existing output file: {output}")
        output.parent.mkdir(parents=True,exist_ok=True)
        tmp=output.with_name(output.stem+f".processing_{uuid.uuid4().hex}.wav")
        cmd=[self._binary(),"-nostdin","-hide_banner","-loglevel","error","-y","-i",str(source),"-filter:a",f"atempo={speed:.5f}","-c:a","pcm_s16le",str(tmp)]
        try:
            p=subprocess.run(cmd,capture_output=True,text=True,timeout=300)
            if p.returncode: raise RuntimeError("FFmpeg speed adjustment failed: "+p.stderr[-1200:])
            inspect_wav(tmp,False); tmp.replace(output); return output
        finally: tmp.unlink(missing_ok=True)
    def change_pitch(self, source:Path, output:Path, semitones:float) -> Path:
        semitones=float(semitones)
        if not -8<=semitones<=8: raise ValueError("Pitch must be between -8 and +8 semitones")
        rate_factor=2.0**(semitones/12.0)
        source=Path(source).expanduser().resolve(); info=inspect_wav(source,False)
        output=Path(output).expanduser().resolve()
        if source==output: raise ValueError("Choose a new output path; the source audio will not be overwritten in place.")
        if output.exists(): raise FileExistsError(f"Refusing to overwrite an existing output file: {output}")
        output.parent.mkdir(parents=True,exist_ok=True)
        tmp=output.with_name(output.stem+f".processing_{uuid.uuid4().hex}.wav")
        # asetrate changes pitch and duration; aresample brings the file back to the original sample rate.
        filt=f"asetrate={info.sample_rate}*{rate_factor:.8f},aresample={info.sample_rate}"
        cmd=[self._binary(),"-nostdin","-hide_banner","-loglevel","error","-y","-i",str(source),"-filter:a",filt,"-c:a","pcm_s16le",str(tmp)]
        try:
            p=subprocess.run(cmd,capture_output=True,text=True,timeout=300)
            if p.returncode: raise RuntimeError("FFmpeg pitch adjustment failed: "+p.stderr[-1200:])
            inspect_wav(tmp,False); tmp.replace(output); return output
        finally: tmp.unlink(missing_ok=True)
