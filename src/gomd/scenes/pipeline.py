from __future__ import annotations
from pathlib import Path
from typing import Callable
from ..audio.processor import PauseSettings, synthesize_with_pauses
from ..audio.wav_tools import concatenate_wavs, inspect_wav
from ..core.project import Project
from ..mathtext.engine import MathTextEngine
from ..pronunciation.dictionary import PronunciationDictionary
from ..tts.base import TTSAdapter, TTSRequest

def synthesize_project_scenes(project: Project, adapter: TTSAdapter, model_path: Path, speed: float=1.0,
                              pauses: PauseSettings|None=None, dictionary: PronunciationDictionary|None=None,
                              text_language: str="ru", overwrite: bool=False, cancel_event=None,
                              progress: Callable[[str],None]|None=None, pitch_semitones: float=0.0) -> list[Path]:
    """Sequentially synthesize every project scene. Existing WAVs are protected unless overwrite=True."""
    if not project.scenes: raise ValueError("Project has no scenes")
    model_path=Path(model_path).expanduser().resolve()
    valid,reason=adapter.validate_model(model_path)
    if not valid: raise FileNotFoundError(reason)
    dictionary=dictionary or PronunciationDictionary(); pauses=pauses or PauseSettings()
    completed=[]
    for index,scene in enumerate(project.scenes,1):
        if cancel_event is not None and cancel_event.is_set(): raise InterruptedError("Batch synthesis cancelled.")
        output=project.scene_dir(scene)/"audio.wav"
        if output.exists() and not overwrite: raise FileExistsError(f"Scene audio already exists; enable overwrite explicitly to replace it: {output}")
        source=scene.text.strip()
        if not source: raise ValueError(f"Scene '{scene.name}' has no source text.")
        norm=scene.normalized_text.strip()
        if not norm: norm=MathTextEngine().normalize(source).text
        lang=str(scene.settings.get("text_language",text_language))
        norm=dictionary.apply(norm,language=lang,engine_id=adapter.id)
        temp=output.with_name(output.stem+".gomd_batch_tmp.wav")
        pitched=output.with_name(output.stem+".gomd_batch_pitched.wav")
        temp.unlink(missing_ok=True); pitched.unlink(missing_ok=True)
        try:
            if progress: progress(f"Synthesizing scene {index}/{len(project.scenes)}: {scene.name}")
            request=TTSRequest(text=norm,output_path=temp,model_path=model_path,speed=speed)
            synthesize_with_pauses(adapter,request,pauses,cancel_event=cancel_event,progress=progress)
            if abs(float(pitch_semitones))>0.001:
                from ..audio.processor import AudioProcessor
                AudioProcessor().change_pitch(temp,pitched,float(pitch_semitones))
                pitched.replace(temp)
            inspect_wav(temp,False)
            if cancel_event is not None and cancel_event.is_set(): raise InterruptedError("Batch synthesis cancelled.")
            if output.exists() and not overwrite: raise FileExistsError(f"Audio appeared during synthesis; refusing to overwrite: {output}")
            temp.replace(output)
            scene.normalized_text=norm; scene.audio_path=str(output.resolve()); scene.status="synthesized"; scene.engine_id=adapter.id; scene.model_path=str(model_path)
            scene.settings["speed"]=float(speed); scene.settings["pitch"]=float(pitch_semitones); scene.settings["text_language"]=lang
            project.save_scene(scene); completed.append(output)
        finally:
            temp.unlink(missing_ok=True); pitched.unlink(missing_ok=True)
    project.save()
    return completed

def assemble_project_audio(project: Project, output_path: Path|None=None, pause_ms: int=400,
                           overwrite: bool=False, target_rate: int|None=None) -> Path:
    sources=[]
    for scene in project.scenes:
        path=Path(scene.audio_path) if scene.audio_path else project.scene_dir(scene)/"audio.wav"
        if not path.is_absolute(): path=project.root/path
        if not path.is_file(): raise FileNotFoundError(f"Scene '{scene.name}' has no available WAV output.")
        sources.append(path.resolve())
    output=Path(output_path).expanduser().resolve() if output_path else (project.root/"exports"/"final.wav").resolve()
    if output.exists() and not overwrite: raise FileExistsError(f"Final WAV already exists; pass overwrite=True after user confirmation: {output}")
    output.parent.mkdir(parents=True,exist_ok=True)
    staging=output.with_name(output.stem+".gomd_assemble_tmp.wav")
    staging.unlink(missing_ok=True)
    try:
        concatenate_wavs(sources,staging,pause_ms=max(0,int(pause_ms)),target_rate=target_rate)
        inspect_wav(staging,False)
        if output.exists() and not overwrite: raise FileExistsError(f"Output appeared during assembly; refusing to overwrite: {output}")
        staging.replace(output)
        return output
    finally: staging.unlink(missing_ok=True)
