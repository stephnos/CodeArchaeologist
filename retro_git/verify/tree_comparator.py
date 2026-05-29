from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from retro_git.scanner.file_collection import collect_project_paths


@dataclass
class TreeDiff:
    missing_in_target: list[str] = field(default_factory=list)
    extra_in_target: list[str] = field(default_factory=list)
    content_mismatch: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.missing_in_target or self.extra_in_target or self.content_mismatch)

    def all_paths_to_sync(self) -> list[str]:
        return sorted(set(self.missing_in_target) | set(self.content_mismatch))


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _collect_hashes(root: Path, paths: list[str]) -> dict[str, str]:
    root = root.resolve()
    out: dict[str, str] = {}
    for rel_str in paths:
        path = root / rel_str
        if path.is_file():
            out[rel_str] = _file_hash(path)
    return out


def compare_trees(
    source: Path,
    target: Path,
    *,
    paths: list[str] | None = None,
    include_secrets: bool = False,
    include_untracked: bool = False,
) -> TreeDiff:
    if paths is None:
        paths = collect_project_paths(
            source,
            include_secrets=include_secrets,
            include_untracked=include_untracked,
        )
    source_map = _collect_hashes(source, paths)
    target_map = _collect_hashes(target, paths)

    diff = TreeDiff()
    source_keys = set(source_map)
    target_keys = set(target_map)

    diff.missing_in_target = sorted(source_keys - target_keys)
    diff.extra_in_target = sorted(target_keys - source_keys)

    for key in sorted(source_keys & target_keys):
        if source_map[key] != target_map[key]:
            diff.content_mismatch.append(key)

    return diff
