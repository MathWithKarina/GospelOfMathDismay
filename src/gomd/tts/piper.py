"""Piper CLI adapter compatible with common Piper command-line builds."""
from __future__ import annotations
import os, shutil, subprocess, time, wave, logging, uuid
from pathlib import Path
from .base import TTSAdapter, TTSCapabilities, TTSRequest, TTSResult
log=logging.getLogger(__name__)

class PiperCLIAdapter(TTSAdapter):
    id="piper-cli"; name="Piper (command line)"
    capabilities=TTSCapabilities(languages=("ru", "en-GB", "other"), supports_speed=True,
        supports_pitch=False, supports_emotion=False, supports_cancellation=True,
        notes="Speed is adjusted with Piper's length_scale. Pitch and emotion are not native CLI controls.")
    def __init__(self, executable: str="piper"):
        self.executable=executable
    def resolved_executable(self) -> str | None:
        candidate=Path(self.executable).expanduser()
        if candidate.is_file(): return str(candidate.resolve())
        return shutil.which(self.executable)
    def is_available(self) -> bool: return self.resolved_executable() is not None
    def validate_model(self, model_path: Path) -> tuple[bool,str]:
        model=Path(model_path).expanduser()
        if not model.is_file() or model.suffix.lower()!=".onnx": return False,"Choose a Piper .onnx model file."
        if not Path(str(model)+".json").is_file(): return False,"The matching .onnx.json model configuration is missing."
        return True,"Piper model and configuration are present."
    def discover_models(self, directory: Path) -> list[Path]:
        folder=Path(directory).expanduser()
        if not folder.is_dir(): return []
        return sorted((p.resolve() for p in folder.glob("*.onnx") if Path(str(p)+".json").is_file()),key=lambda p:p.name.casefold())
    def version_text(self) -> str:
        exe=self.resolved_executable()
        if not exe: return "Piper executable was not found."
        try:
            p=subprocess.run([exe,"--help"],capture_output=True,text=True,timeout=5,check=False)
            return (p.stdout or p.stderr)[:3000]
        except (OSError,subprocess.TimeoutExpired) as exc: return f"Unable to query Piper: {exc}"
    def synthesize(self, request: TTSRequest, cancel_event=None, progress=None) -> TTSResult:
        exe=self.resolved_executable()
        if not exe: raise FileNotFoundError("Piper was not found. Set its path in Settings, then check it again.")
        model=Path(request.model_path).expanduser().resolve()
        if not model.is_file() or model.suffix.lower()!=".onnx": raise FileNotFoundError(f"Piper ONNX model not found: {model}")
        config=Path(str(model)+".json")
        if not config.is_file(): raise FileNotFoundError(f"Missing model sidecar config: {config.name}")
        if not request.text.strip(): raise ValueError("Text is empty; nothing to synthesize.")
        output=Path(request.output_path).expanduser().resolve()
        output.parent.mkdir(parents=True,exist_ok=True)
        if output.exists(): raise FileExistsError(f"Refusing to overwrite an existing output file: {output}")
        temp_output=output.with_name(output.stem+".piper_"+uuid.uuid4().hex+output.suffix)
        rate=min(2.0,max(0.5,float(request.speed)))
        length_scale=1.0/rate
        cmd=[exe,"--model",str(model),"--output_file",str(temp_output),"--length_scale",f"{length_scale:.4f}"]
        if request.speaker_id is not None: cmd.extend(["--speaker",str(int(request.speaker_id))])
        for key,value in request.extra_options.items():
            if key in {"noise_scale","noise_w","sentence_silence"}:
                cmd.extend(["--"+key.replace("_","-"),str(float(value))])
        started=time.monotonic()
        if progress: progress("Starting Piper synthesis…")
        proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding="utf-8",errors="replace")
        try:
            pending_input=True
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    proc.terminate()
                    try: proc.communicate(timeout=2)
                    except subprocess.TimeoutExpired: proc.kill(); proc.communicate()
                    raise InterruptedError("Synthesis cancelled.")
                try:
                    if pending_input:
                        stdout,stderr=proc.communicate(request.text,timeout=0.25)
                        pending_input=False
                    else:
                        stdout,stderr=proc.communicate(timeout=0.25)
                    break
                except subprocess.TimeoutExpired:
                    pending_input=False
                    continue
            if proc.returncode != 0:
                log.error("Piper returned %s: %s",proc.returncode,stderr[-2000:])
                raise RuntimeError(f"Piper failed (exit code {proc.returncode}). Check engine and model compatibility.\n{stderr[-1200:]}")
            if cancel_event is not None and cancel_event.is_set(): raise InterruptedError("Synthesis cancelled.")
            if not temp_output.is_file() or temp_output.stat().st_size < 44:
                raise RuntimeError("Piper finished without producing a valid WAV file.")
            try:
                with wave.open(str(temp_output),"rb") as w:
                    if w.getnframes() <= 0 or w.getnchannels() not in (1,2): raise ValueError("empty/unsupported WAV")
                    duration=w.getnframes()/float(w.getframerate())
            except (wave.Error,EOFError) as exc: raise RuntimeError(f"Piper output is not a readable PCM WAV: {exc}") from exc
            if output.exists(): raise FileExistsError(f"Output appeared during synthesis; refusing to overwrite: {output}")
            temp_output.replace(output)
            if progress: progress("Audio file verified.")
            return TTSResult(output,duration,self.id,model,(stdout+"\n"+stderr).strip(),{"elapsed_seconds":time.monotonic()-started,"speed":rate})
        except BaseException:
            if proc.poll() is None:
                proc.kill()
                try: proc.communicate()
                except Exception: pass
            raise
        finally:
            temp_output.unlink(missing_ok=True)
