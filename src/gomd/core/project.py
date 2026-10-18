"""Atomic, path-safe project and scene persistence."""
from __future__ import annotations
import json, re, shutil, uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_FORMAT = 1

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def _safe_name(value: str) -> str:
    value = re.sub(r"[^\w .-]+", "_", value, flags=re.UNICODE).strip(" .")
    return (value[:80] or "scene")

def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)

@dataclass
class Scene:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = "Scene"
    text: str = ""
    normalized_text: str = ""
    audio_path: str = ""
    status: str = "draft"
    engine_id: str = "piper-cli"
    model_path: str = ""
    settings: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

@dataclass
class Project:
    name: str
    root: Path
    scenes: list[Scene] = field(default_factory=list)
    media: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    @classmethod
    def create(cls, root: Path, name: str) -> "Project":
        root = Path(root).expanduser().resolve()
        if root.exists() and any(root.iterdir()):
            raise FileExistsError(f"Project directory is not empty: {root}")
        root.mkdir(parents=True, exist_ok=True)
        (root / "scenes").mkdir(exist_ok=True)
        (root / "media").mkdir(exist_ok=True)
        (root / "exports").mkdir(exist_ok=True)
        project = cls(name=_safe_name(name), root=root)
        project.add_scene("Scene 001")
        project.save()
        return project

    @classmethod
    def open(cls, root: Path) -> "Project":
        root = Path(root).expanduser().resolve()
        descriptor = root / "project.json"
        raw = json.loads(descriptor.read_text(encoding="utf-8"))
        if raw.get("format_version") != PROJECT_FORMAT:
            raise ValueError(f"Unsupported project format: {raw.get('format_version')}")
        project = cls(name=str(raw["name"]), root=root, scenes=[Scene(**s) for s in raw.get("scenes", [])],
                      media=list(raw.get("media", [])), created_at=raw.get("created_at", _now()),
                      updated_at=raw.get("updated_at", _now()))
        # Scene contents are stored separately and are the canonical editable copies.
        for scene in project.scenes:
            directory = project.scene_dir(scene)
            text_file, normalized_file, meta_file = directory / "text.txt", directory / "normalized.txt", directory / "metadata.json"
            if text_file.exists(): scene.text = text_file.read_text(encoding="utf-8")
            if normalized_file.exists(): scene.normalized_text = normalized_file.read_text(encoding="utf-8")
            if meta_file.exists():
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                scene.audio_path = meta.get("audio_path", scene.audio_path)
                scene.status = meta.get("status", scene.status)
                scene.engine_id = meta.get("engine_id", scene.engine_id)
                scene.model_path = meta.get("model_path", scene.model_path)
                scene.settings = meta.get("settings", scene.settings)
        return project

    def scene_dir(self, scene: Scene) -> Path:
        # IDs are generated internally; resolve+parent check prevents path traversal.
        base = (self.root / "scenes").resolve()
        target = (base / scene.id).resolve()
        if target.parent != base:
            raise ValueError("Invalid scene path")
        return target

    def add_scene(self, name: str | None = None, clone: Scene | None = None) -> Scene:
        number = len(self.scenes) + 1
        scene = Scene(name=_safe_name(name or (f"Scene {number:03d}")), text=clone.text if clone else "",
                      normalized_text=clone.normalized_text if clone else "",
                      engine_id=clone.engine_id if clone else "piper-cli", model_path=clone.model_path if clone else "",
                      settings=dict(clone.settings) if clone else {})
        self.scenes.append(scene)
        self.save_scene(scene)
        self.save()
        return scene

    def save_scene(self, scene: Scene) -> None:
        if not any(s.id == scene.id for s in self.scenes):
            raise ValueError("Scene does not belong to this project")
        folder = self.scene_dir(scene)
        folder.mkdir(parents=True, exist_ok=True)
        scene.updated_at = _now()
        (folder / "text.txt").write_text(scene.text, encoding="utf-8")
        (folder / "normalized.txt").write_text(scene.normalized_text, encoding="utf-8")
        _atomic_json(folder / "metadata.json", {"id": scene.id, "name": scene.name, "audio_path": scene.audio_path,
                    "status": scene.status, "engine_id": scene.engine_id, "model_path": scene.model_path,
                    "settings": scene.settings, "created_at": scene.created_at, "updated_at": scene.updated_at})

    def delete_scene(self, scene_id: str) -> None:
        if len(self.scenes) <= 1:
            raise ValueError("A project must retain at least one scene")
        scene = next((s for s in self.scenes if s.id == scene_id), None)
        if scene is None: raise KeyError(scene_id)
        # Scene deletion removes only the app-managed scene directory, never audio_path external files.
        directory = self.scene_dir(scene)
        self.scenes = [s for s in self.scenes if s.id != scene_id]
        if directory.exists(): shutil.rmtree(directory)
        self.save()

    def move_scene(self, scene_id: str, delta: int) -> None:
        index = next((i for i, s in enumerate(self.scenes) if s.id == scene_id), None)
        if index is None: raise KeyError(scene_id)
        target = index + int(delta)
        if 0 <= target < len(self.scenes):
            self.scenes[index], self.scenes[target] = self.scenes[target], self.scenes[index]
            self.save()

    def save(self) -> None:
        self.updated_at = _now()
        for scene in self.scenes:
            self.save_scene(scene)
        _atomic_json(self.root / "project.json", {"format_version": PROJECT_FORMAT, "name": self.name,
            "created_at": self.created_at, "updated_at": self.updated_at, "scenes": [asdict(s) for s in self.scenes], "media": self.media})

    def add_media(self, file_path: Path) -> Path:
        source = Path(file_path).expanduser().resolve()
        if not source.is_file(): raise FileNotFoundError(source)
        target = (self.root / "media" / source.name).resolve()
        if target.parent != (self.root / "media").resolve(): raise ValueError("Invalid media path")
        if source != target:
            if target.exists():
                target = target.with_name(f"{target.stem}_{uuid.uuid4().hex[:6]}{target.suffix}")
            shutil.copy2(source, target)
        rel = str(target.relative_to(self.root))
        if rel not in self.media: self.media.append(rel)
        self.save()
        return target
