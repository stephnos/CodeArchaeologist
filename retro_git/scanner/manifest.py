from __future__ import annotations

import json
from pathlib import Path

from retro_git.models import Manifest
from retro_git.scanner.codebase_scanner import detect_stack_hints
from retro_git.scanner.file_collection import collect_project_paths, paths_to_entries


def build_manifest(
    source: Path,
    *,
    include_secrets: bool = False,
    include_untracked: bool = False,
) -> Manifest:
    source = source.resolve()
    paths = collect_project_paths(
        source,
        include_secrets=include_secrets,
        include_untracked=include_untracked,
    )
    files = paths_to_entries(source, paths)
    stack_hints = detect_stack_hints(source, files)
    total = sum(f.size_bytes for f in files)
    return Manifest(
        root=str(source),
        files=files,
        stack_hints=stack_hints,
        total_bytes=total,
    )


def manifest_for_llm(manifest: Manifest) -> list[dict[str, object]]:
    return [
        {
            "path": f.path,
            "size_bytes": f.size_bytes,
            "extension": f.extension,
        }
        for f in manifest.files
    ]


def manifest_to_tree_text(manifest: Manifest, max_lines: int = 200) -> str:
    paths = sorted(manifest.paths())
    lines: list[str] = []
    for path in paths[:max_lines]:
        lines.append(path)
    if len(paths) > max_lines:
        lines.append(f"... ({len(paths) - max_lines} more files)")
    return "\n".join(lines)


def save_manifest_cache(target: Path, manifest: Manifest) -> Path:
    cache_dir = target / ".retro-git"
    cache_dir.mkdir(parents=True, exist_ok=True)
    out = cache_dir / "manifest.json"
    payload = {
        "root": manifest.root,
        "stack_hints": manifest.stack_hints,
        "total_bytes": manifest.total_bytes,
        "files": [f.model_dump() for f in manifest.files],
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out
