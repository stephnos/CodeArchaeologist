from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from retro_git.config import DEFAULT_IGNORE_FILES


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


def _should_skip(relative: Path) -> bool:
    if relative.name in DEFAULT_IGNORE_FILES:
        return True
    if ".git" in relative.parts:
        return True
    if ".retro-git" in relative.parts:
        return True
    return False


def _collect_hashes(root: Path) -> dict[str, str]:
    root = root.resolve()
    out: dict[str, str] = {}
    if not root.is_dir():
        return out
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if _should_skip(rel):
            continue
        out[rel.as_posix()] = _file_hash(path)
    return out


def compare_trees(source: Path, target: Path) -> TreeDiff:
    source_map = _collect_hashes(source)
    target_map = _collect_hashes(target)

    diff = TreeDiff()
    source_keys = set(source_map)
    target_keys = set(target_map)

    diff.missing_in_target = sorted(source_keys - target_keys)
    diff.extra_in_target = sorted(target_keys - source_keys)

    for key in sorted(source_keys & target_keys):
        if source_map[key] != target_map[key]:
            diff.content_mismatch.append(key)

    return diff
