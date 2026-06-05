from __future__ import annotations

import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from retro_git.layout import old_workspaces_root

_OLD_NAME = re.compile(r"^.+\.old(\.\d+)?$")


def is_old_backup_name(name: str) -> bool:
    return bool(_OLD_NAME.match(name))


def discover_old_backups(old_dir: str | Path | None = None) -> tuple[list[dict[str, str]], str]:
    """List backup folders under the old-workspaces root."""
    root = Path(old_dir).expanduser().resolve() if old_dir else old_workspaces_root()
    if not root.is_dir():
        raise ValueError(f"Old backups folder not found: {root}")

    backups: list[dict[str, str]] = []
    for entry in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if not entry.is_dir() or not is_old_backup_name(entry.name):
            continue
        modified = datetime.fromtimestamp(entry.stat().st_mtime, tz=timezone.utc)
        backups.append(
            {
                "name": entry.name,
                "path": str(entry.resolve()),
                "modified": modified.strftime("%Y-%m-%d %H:%M"),
            }
        )
    return backups, str(root)


def delete_old_backup(backup_path: str | Path, old_dir: str | Path) -> None:
    """Permanently remove one backup directory."""
    root = Path(old_dir).expanduser().resolve()
    backup = Path(backup_path).expanduser().resolve()

    if not root.is_dir():
        raise ValueError(f"Old backups folder not found: {root}")
    if not backup.is_dir():
        raise ValueError(f"Not a directory: {backup}")
    if not is_old_backup_name(backup.name):
        raise ValueError(f"Not an old backup name: {backup.name}")
    try:
        backup.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Backup must be inside {root}") from exc

    shutil.rmtree(backup)
