from __future__ import annotations
import os, zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT.parent/"GospelOfMathDismay.zip"
EXCLUDED={".git",".venv","venv","__pycache__",".pytest_cache",".mypy_cache",".ruff_cache","node_modules","dist","build",".tox",".nox"}
EXCLUDED_FILES={".DS_Store","Thumbs.db","desktop.ini","*.pyc","*.pyo","*.log","*.tmp"}
def allowed(path:Path)->bool:
    relative=path.relative_to(ROOT)
    if any(part in EXCLUDED or part.endswith(".egg-info") for part in relative.parts): return False
    if path.is_symlink(): return False
    if path.suffix in {".pyc",".pyo",".log",".tmp",".bak"} or path.name==".coverage": return False
    return path.is_file()
def main():
    if OUT.exists(): OUT.unlink()
    files=sorted(p for p in ROOT.rglob("*") if allowed(p))
    with zipfile.ZipFile(OUT,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=8) as zf:
        for path in files: zf.write(path,Path(ROOT.name)/path.relative_to(ROOT))
    with zipfile.ZipFile(OUT) as zf:
        bad=zf.testzip()
        if bad: raise RuntimeError(f"Corrupt ZIP member: {bad}")
        names=zf.namelist()
        for required in ("README.md","LICENSE","NOTICE","pyproject.toml","src/gomd/__main__.py","tests/test_mathtext.py"):
            if f"{ROOT.name}/{required}" not in names: raise RuntimeError(f"Missing required archive file: {required}")
    print(f"Created {OUT} ({OUT.stat().st_size:,} bytes, {len(files)} files)")
if __name__=="__main__": main()
