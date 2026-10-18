"""Vocal α music-sequence editor data model and honest synthesized-tone preview.

This is NOT a neural singing voice. The preview is a simple oscillator that helps check note timing.
"""
from __future__ import annotations
import json, math, struct, wave
from dataclasses import asdict, dataclass, field
from pathlib import Path

@dataclass
class Note:
    start_beats: float
    duration_beats: float
    midi_note: int = 60
    syllable: str = "la"
    velocity: float = 0.8
    def __post_init__(self):
        if self.start_beats<0 or self.duration_beats<=0: raise ValueError("A note must start at or after beat 0 and have positive duration")
        if not 24<=self.midi_note<=108: raise ValueError("MIDI note must be between 24 and 108")
        if not 0<=self.velocity<=1: raise ValueError("Velocity must be between 0 and 1")

@dataclass
class VocalProject:
    title: str="Vocal α sketch"
    bpm: int=100
    notes: list[Note]=field(default_factory=list)
    version: str="0.0.0.1"
    def __post_init__(self):
        if not 30<=self.bpm<=240: raise ValueError("Tempo must be between 30 and 240 BPM")
    def save(self,path:Path):
        target=Path(path).resolve(); target.parent.mkdir(parents=True,exist_ok=True)
        temp=target.with_suffix(target.suffix+".tmp")
        temp.write_text(json.dumps({"format_version":1,"title":self.title,"bpm":self.bpm,"version":self.version,"notes":[asdict(n) for n in self.notes]},ensure_ascii=False,indent=2),encoding="utf-8")
        temp.replace(target)
    @classmethod
    def load(cls,path:Path):
        d=json.loads(Path(path).read_text(encoding="utf-8"))
        if d.get("format_version")!=1: raise ValueError("Unsupported Vocal α project format")
        return cls(title=d.get("title","Vocal α sketch"),bpm=int(d.get("bpm",100)),notes=[Note(**x) for x in d.get("notes",[])],version=d.get("version","0.0.0.1"))

def render_preview_wav(project:VocalProject, output:Path, sample_rate:int=22050) -> Path:
    """Render monophonic sine-tone notes with short envelopes; this is a timing preview, not singing."""
    if not project.notes: raise ValueError("Add at least one note before previewing")
    seconds_per_beat=60/project.bpm; end=max(n.start_beats+n.duration_beats for n in project.notes)*seconds_per_beat
    total=min(int(end*sample_rate),sample_rate*600)
    samples=[0.0]*total
    for note in project.notes:
        start=int(note.start_beats*seconds_per_beat*sample_rate); length=int(note.duration_beats*seconds_per_beat*sample_rate)
        freq=440*2**((note.midi_note-69)/12)
        attack=max(1,int(.015*sample_rate)); release=max(1,int(.04*sample_rate))
        for i in range(max(0,min(length,total-start))):
            env=min(1.0,i/attack,(length-i)/release)
            value=math.sin(2*math.pi*freq*i/sample_rate)*max(0.0,env)*note.velocity*.4
            samples[start+i]=max(-1.0,min(1.0,samples[start+i]+value))
    output=Path(output).expanduser().resolve(); output.parent.mkdir(parents=True,exist_ok=True)
    tmp=output.with_suffix(".tmp.wav")
    with wave.open(str(tmp),"wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sample_rate)
        data=b"".join(struct.pack("<h",int(max(-1.0,min(1.0,s))*32767)) for s in samples)
        w.writeframes(data)
    tmp.replace(output); return output
