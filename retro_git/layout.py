from __future__ import annotations

import shutil
import os
from dataclasses import dataclass
from pathlib import Path

import typer


@dataclass(frozen=True)
class ResolvedLayout:
    """Paths for scan, file copy source, and git output."""

    scan_root: Path
    staging_source: Path
    target: Path
    force: bool
    relocate_to_old: bool

    @property
    def backup_path(self) -> Path:
        return old_workspaces_root() / f"{self.scan_root.name}.old"


def old_workspaces_root() -> Path:
    """
    Folder where .old workspace backups are stored.

    Default: ~/projects/software-engineering/.old
    Override with RETRO_GIT_OLD_ROOT.
    """
    env = os.getenv("RETRO_GIT_OLD_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    return Path.home() / "projects" / "software-engineering" / ".old"


def resolve_layout(source_text: str, target_text: str) -> tuple[ResolvedLayout | None, str | None]:
    source_text = source_text.strip()
    if not source_text:
        return None, "Source directory is required."

    scan_root = Path(source_text).expanduser().resolve()
    if not scan_root.is_dir():
        return None, f"Source folder not found: {scan_root}"

    target_text = target_text.strip()
    if target_text:
        target = Path(target_text).expanduser().resolve()
        if target == scan_root:
            return None, (
                "Target cannot be the same as source. Leave target blank to replace "
                "the project in place (original moved to .old/<name>.old)."
            )
        return (
            ResolvedLayout(
                scan_root=scan_root,
                staging_source=scan_root,
                target=target,
                force=False,
                relocate_to_old=False,
            ),
            None,
        )

    # Blank target: move project to .old/<name>.old, build new repo at original path.
    return (
        ResolvedLayout(
            scan_root=scan_root,
            staging_source=scan_root,
            target=scan_root,
            force=False,
            relocate_to_old=True,
        ),
        None,
    )


def apply_relocate(layout: ResolvedLayout) -> Path:
    """Move scan_root to <name>.old; return path used to read files for commits."""
    backup = layout.backup_path
    backup.parent.mkdir(parents=True, exist_ok=True)
    if backup.exists():
        idx = 2
        while True:
            candidate = backup.parent / f"{layout.scan_root.name}.old.{idx}"
            if not candidate.exists():
                backup = candidate
                break
            idx += 1
    shutil.move(str(layout.scan_root), str(backup))
    layout.target.mkdir(parents=True, exist_ok=True)
    return backup
