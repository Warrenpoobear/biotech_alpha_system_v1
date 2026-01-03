from __future__ import annotations
import hashlib
from pathlib import Path
from typing import Dict, List

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()

def build_manifest(fixtures_dir: Path, artifacts_dir: Path) -> Dict:
    fixtures = []
    for p in sorted(fixtures_dir.glob("*")):
        if p.is_file() and not p.name.endswith(".sha256"):
            fixtures.append({"path": str(p), "sha256": sha256_file(p)})

    artifacts = []
    for p in sorted(artifacts_dir.rglob("*")):
        if p.is_file() and not p.name.endswith(".sha256"):
            artifacts.append({"path": str(p.relative_to(artifacts_dir)), "sha256": sha256_file(p)})

    return {"fixtures": fixtures, "artifacts": artifacts}
