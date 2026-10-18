"""Real Piper voice catalog client using Hugging Face's public HTTPS API."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib, json, logging, os, re, tempfile, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

log=logging.getLogger(__name__)
REPO="rhasspy/piper-voices"
API_ROOT=f"https://huggingface.co/api/models/{REPO}/tree/main"
RAW_ROOT=f"https://huggingface.co/{REPO}/resolve/main/"

class DownloadCancelled(Exception): pass

@dataclass
class VoiceModel:
    model_id: str
    name: str
    language_code: str
    quality: str
    model_url: str
    config_url: str
    license_url: str
    source_url: str
    size_bytes: int | None = None
    sha256: str = ""
    license_text: str = "Unverified: inspect the model card before commercial use or redistribution."
    installed: bool = False
    installed_path: str = ""
    checked_at: str = ""
    author: str = "See model card"

    @property
    def size_label(self):
        return f"{self.size_bytes / (1024*1024):.1f} MiB" if self.size_bytes else "size unknown"

class ModelCatalogClient:
    def __init__(self, timeout: int=20, user_agent: str="GospelOfMathDismay/0.1.0"):
        self.timeout=timeout; self.user_agent=user_agent
    def _json(self,url:str):
        request=Request(url,headers={"User-Agent":self.user_agent,"Accept":"application/json"})
        with urlopen(request,timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    def search(self, language_filter: str="", query: str="", progress: Callable[[str],None] | None=None) -> list[VoiceModel]:
        """Fetch the remote catalog; errors are raised and must be shown as errors by the UI."""
        if progress: progress("Fetching the live voice catalog from Hugging Face…")
        entries=[]; url=API_ROOT+"?recursive=true&expand=true&limit=1000"
        pages=0
        while url and pages<20:
            data=self._json(url); pages+=1
            if not isinstance(data,list): raise RuntimeError("Unexpected response from Hugging Face catalog API")
            entries.extend(x for x in data if isinstance(x,dict))
            # Pagination links are not consistently exposed by urllib; API tree calls normally fit here.
            if len(data)<1000: break
            cursor=data[-1].get("path") or data[-1].get("oid")
            if not cursor: break
            url=API_ROOT+"?recursive=true&expand=true&limit=1000&cursor="+quote(str(cursor),safe="")
        files={x.get("path"):x for x in entries if x.get("type")=="file" and isinstance(x.get("path"),str)}
        models=[]; needle=query.casefold().strip(); lang=language_filter.casefold().strip()
        for path,item in files.items():
            if not path.endswith(".onnx"): continue
            base=path[:-5]; config=base+".onnx.json"
            if config not in files: continue
            segment=Path(path)
            code=next((part for part in segment.parts if re.fullmatch(r"[a-z]{2}_[A-Z]{2}",part)), "unknown")
            if lang and not (code.casefold().startswith(lang) or (lang=="ru" and code=="ru_RU") or (lang in {"en","en-gb","en-gb"} and code=="en_GB")): continue
            name=segment.name[:-5]
            if needle and needle not in (name+" "+path).casefold(): continue
            folder=str(segment.parent)
            card_path=folder+"/MODEL_CARD"
            card_exists=card_path in files
            size=item.get("size")
            lfs=item.get("lfs") if isinstance(item.get("lfs"),dict) else {}
            remote_hash=str(lfs.get("sha256") or lfs.get("oid") or "")
            if remote_hash.startswith("sha256:"): remote_hash=remote_hash.split(":",1)[1]
            if not re.fullmatch(r"[0-9a-fA-F]{64}",remote_hash): remote_hash=""
            models.append(VoiceModel(model_id=path,name=name,language_code=code,quality=segment.parent.name,
                model_url=RAW_ROOT+quote(path,safe="/"),config_url=RAW_ROOT+quote(config,safe="/"),
                license_url=(RAW_ROOT+quote(card_path,safe="/") if card_exists else "https://huggingface.co/"+REPO),
                source_url="https://huggingface.co/"+REPO+"/tree/main/"+quote(folder,safe="/"),
                size_bytes=int(size) if isinstance(size,(int,float)) else None,sha256=remote_hash,
                checked_at=datetime.now(timezone.utc).isoformat(timespec="seconds")))
        models.sort(key=lambda m:(m.language_code,m.name.casefold()))
        if progress: progress(f"Catalog loaded: {len(models)} compatible model files found.")
        return models
    def fetch_license_text(self, model: VoiceModel) -> str:
        try:
            request=Request(model.license_url,headers={"User-Agent":self.user_agent})
            with urlopen(request,timeout=self.timeout) as r: text=r.read(400_000).decode("utf-8",errors="replace")
            # Hugging Face raw URLs may render HTML if no /resolve prefix.
            return text[:12000]
        except (OSError,HTTPError,URLError) as exc:
            return f"Could not fetch model card: {exc}. Open {model.license_url} and inspect the license manually."
    def download(self, model: VoiceModel, directory: Path, cancel_event=None,
                 progress: Callable[[int|None,int|None,str],None] | None=None) -> Path:
        """Download both model files to temporary files; commit only after both finish."""
        directory=Path(directory).expanduser().resolve(); directory.mkdir(parents=True,exist_ok=True)
        safe_name=re.sub(r"[^A-Za-z0-9_.-]","_",model.name)
        final_model=(directory/(safe_name+".onnx")).resolve(); final_cfg=(directory/(safe_name+".onnx.json")).resolve()
        if final_model.parent!=directory or final_cfg.parent!=directory: raise ValueError("Invalid model filename")
        if final_model.exists() and final_cfg.exists(): return final_model
        temps=[]
        try:
            for url,final in ((model.model_url,final_model),(model.config_url,final_cfg)):
                tmp=final.with_name(final.name+".download")
                tmp.unlink(missing_ok=True); temps.append((tmp,final))
                req=Request(url,headers={"User-Agent":self.user_agent})
                with urlopen(req,timeout=self.timeout) as response, tmp.open("wb") as handle:
                    total=int(response.headers.get("Content-Length") or 0) or None; done=0; digest=hashlib.sha256()
                    while True:
                        if cancel_event is not None and cancel_event.is_set(): raise DownloadCancelled("Download cancelled by user")
                        chunk=response.read(1024*256)
                        if not chunk: break
                        handle.write(chunk); digest.update(chunk); done+=len(chunk)
                        if progress: progress(done,total,final.name)
                if tmp.stat().st_size<8: raise RuntimeError(f"Downloaded file is unexpectedly small: {final.name}")
                if final==final_model and model.sha256 and digest.hexdigest().lower()!=model.sha256.lower():
                    raise RuntimeError("Downloaded voice model failed its SHA-256 check; the file was not installed.")
            # Basic structural sanity before the files become visible as installed.
            cfg=json.loads(temps[1][0].read_text(encoding="utf-8"))
            if not isinstance(cfg,dict) or "audio" not in cfg: raise RuntimeError("The downloaded model configuration is not valid Piper metadata.")
            if temps[0][0].read_bytes()[:4] != b"\x08\x01\x12\x00" and temps[0][0].stat().st_size < 1_000_000:
                raise RuntimeError("The downloaded ONNX file did not pass the basic size check.")
            # Atomic per-file moves; keep a backup when repairing a partial installation.
            for tmp,final in temps:
                tmp.replace(final)
            card_text=self.fetch_license_text(model)
            metadata={"model_id":model.model_id,"name":model.name,"language_code":model.language_code,"quality":model.quality,
                "source_url":model.source_url,"model_url":model.model_url,"config_url":model.config_url,"license_url":model.license_url,
                "license_status":"Model card downloaded; its legal terms still require user review.","license_text":card_text[:12000],
                "checked_at":model.checked_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "installed_at":datetime.now(timezone.utc).isoformat(timespec="seconds"),"sha256":model.sha256 or None}
            metadata_path=directory/(safe_name+".metadata.json")
            metadata_tmp=metadata_path.with_suffix(".metadata.json.tmp")
            metadata_tmp.write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding="utf-8")
            metadata_tmp.replace(metadata_path)
            return final_model
        except BaseException:
            for tmp,_ in temps: tmp.unlink(missing_ok=True)
            raise
