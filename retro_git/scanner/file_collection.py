from __future__ import annotations

import subprocess
from pathlib import Path

from retro_git.config import DEFAULT_IGNORE_DIRS, DEFAULT_IGNORE_FILES, DEFAULT_IGNORE_GLOBS
from retro_git.models import FileEntry
from retro_git.scanner.codebase_scanner import _should_ignore


def is_git_repository(root: Path) -> bool:
    root = root.resolve()
    return (root / ".git").is_dir()


def _git_ls_files(root: Path, *, tracked_only: bool) -> list[str]:
    if tracked_only:
        args = ["git", "-C", str(root), "ls-files", "-z", "--full-name", "-c"]
    else:
        args = [
            "git",
            "-C",
            str(root),
            "ls-files",
            "-z",
            "--full-name",
            "-c",
            "-o",
            "--exclude-standard",
        ]
    result = subprocess.run(args, capture_output=True)
    if result.returncode != 0:
        return []
    raw = result.stdout
    if not raw:
        return []
    return [p.decode("utf-8", errors="replace") for p in raw.split(b"\0") if p]


def _filter_paths(
    root: Path,
    paths: list[str],
    *,
    include_secrets: bool,
) -> list[str]:
    kept: list[str] = []
    for rel_str in paths:
        relative = Path(rel_str)
        if any(part in DEFAULT_IGNORE_DIRS for part in relative.parts):
            continue
        if relative.name in DEFAULT_IGNORE_FILES:
            continue
        if _should_ignore(relative, include_secrets):
            continue
        full = root / relative
        if not full.is_file():
            continue
        kept.append(relative.as_posix())
    return sorted(set(kept))


def collect_project_paths(
    root: Path,
    *,
    include_secrets: bool = False,
    include_untracked: bool = False,
) -> list[str]:
    """
    Paths to include in manifest / verification.

    Git repos default to tracked files only so build artifacts on disk
    are not swept into generated history.
    """
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"source is not a directory: {root}")

    if is_git_repository(root):
        if include_untracked:
            paths = _git_ls_files(root, tracked_only=False)
        else:
            paths = _git_ls_files(root, tracked_only=True)
        return _filter_paths(root, paths, include_secrets=include_secrets)

    entries = scan_filesystem(root, include_secrets=include_secrets)
    return [e.path for e in entries]


def scan_filesystem(
    root: Path,
    *,
    include_secrets: bool = False,
) -> list[FileEntry]:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"source is not a directory: {root}")

    entries: list[FileEntry] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if _should_ignore(relative, include_secrets):
            continue
        stat = path.stat()
        entries.append(
            FileEntry(
                path=relative.as_posix(),
                size_bytes=stat.st_size,
                extension=path.suffix.lower(),
            )
        )
    return entries


def paths_to_entries(root: Path, paths: list[str]) -> list[FileEntry]:
    root = root.resolve()
    entries: list[FileEntry] = []
    for rel_str in paths:
        path = root / rel_str
        if not path.is_file():
            continue
        stat = path.stat()
        entries.append(
            FileEntry(
                path=rel_str,
                size_bytes=stat.st_size,
                extension=path.suffix.lower(),
            )
        )
    return entries
