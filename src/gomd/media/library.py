from __future__ import annotations
from dataclasses import dataclass
import shutil
from pathlib import Path
from ..audio.wav_tools import inspect_wav

@dataclass
class MediaItem:
    path: Path
    name: str
    extension: str
    size_bytes: int
    duration_seconds: float | None = None
    sample_rate: int | None = None
    channels: int | None = None
    status: str = ""

class MediaLibrary:
    AUDIO_EXTENSIONS={".wav"}
    def scan(self, root: Path, recursive: bool=True) -> list[MediaItem]:
        root=Path(root).expanduser().resolve()
        if not root.is_dir(): raise NotADirectoryError(root)
        iterator=root.rglob("*") if recursive else root.iterdir()
        items=[]
        for p in iterator:
            if not p.is_file() or p.suffix.lower() not in self.AUDIO_EXTENSIONS: continue
            try:
                info=inspect_wav(p,False)
                items.append(MediaItem(p,p.name,p.suffix.lower(),p.stat().st_size,info.duration_seconds,info.sample_rate,info.channels))
            except (OSError,ValueError) as exc:
                items.append(MediaItem(p,p.name,p.suffix.lower(),p.stat().st_size,status=f"Unreadable WAV: {exc}"))
        return sorted(items,key=lambda x:x.name.casefold())
    def search(self, items: list[MediaItem], query: str):
        q=query.casefold().strip()
        return [x for x in items if q in x.name.casefold() or q in str(x.path).casefold()]
    def copy(self, source: Path, destination_dir: Path) -> Path:
        source=Path(source).resolve(); destination_dir=Path(destination_dir).expanduser().resolve()
        if not source.is_file(): raise FileNotFoundError(source)
        destination_dir.mkdir(parents=True,exist_ok=True)
        dest=destination_dir/source.name
        if dest.exists(): raise FileExistsError(dest)
        return Path(shutil.copy2(source,dest))
    def move(self, source: Path, destination_dir: Path) -> Path:
        source=Path(source).resolve(); destination_dir=Path(destination_dir).expanduser().resolve()
        if not source.is_file(): raise FileNotFoundError(source)
        destination_dir.mkdir(parents=True,exist_ok=True); dest=destination_dir/source.name
        if dest.exists(): raise FileExistsError(dest)
        return Path(shutil.move(str(source),str(dest)))
    def rename(self, source: Path, new_name: str) -> Path:
        source=Path(source).resolve(); name=Path(new_name)
        if name.name!=new_name or new_name in (".","..") or not new_name.strip(): raise ValueError("Enter a filename, not a path")
        dest=source.with_name(new_name)
        if dest.exists(): raise FileExistsError(dest)
        return source.rename(dest)
    def delete(self, source: Path, confirmed: bool=False) -> None:
        if not confirmed: raise PermissionError("Deletion requires explicit confirmation")
        source=Path(source).resolve()
        if not source.is_file(): raise FileNotFoundError(source)
        source.unlink()
