from __future__ import annotations

import shutil
from pathlib import Path


def stage_files(source_root: Path, target_root: Path, relative_paths: list[str]) -> list[str]:
    source_root = source_root.resolve()
    target_root = target_root.resolve()
    staged: list[str] = []

    for rel in relative_paths:
        rel = rel.replace("\\", "/")
        src = source_root / rel
        dst = target_root / rel
        if not src.is_file():
            raise FileNotFoundError(f"source file missing: {src}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        staged.append(rel)
    return staged
