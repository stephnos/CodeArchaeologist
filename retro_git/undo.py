from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

from rich.console import Console

from retro_git.github_publish import (
    GitHubPublishError,
    default_github_owner,
    undo_github_publish,
)

console = Console()

UNDO_DIR = Path.home() / ".retro-git"
UNDO_FILE = UNDO_DIR / "last-run.json"


class UndoError(Exception):
    pass


@dataclass
class UndoRecord:
    """Snapshot of the last completed generate run (for undo)."""

    project_path: str
    backup_path: str | None
    relocated: bool
    separate_target: str | None
    published_github: bool
    github_owner: str | None
    github_repo: str | None

    @property
    def project(self) -> Path:
        return Path(self.project_path)

    @property
    def backup(self) -> Path | None:
        return Path(self.backup_path) if self.backup_path else None


def save_undo_record(record: UndoRecord) -> None:
    UNDO_DIR.mkdir(parents=True, exist_ok=True)
    UNDO_FILE.write_text(json.dumps(asdict(record), indent=2), encoding="utf-8")


def load_undo_record() -> UndoRecord | None:
    if not UNDO_FILE.is_file():
        return None
    try:
        data = json.loads(UNDO_FILE.read_text(encoding="utf-8"))
        return UndoRecord(**data)
    except (json.JSONDecodeError, TypeError):
        return None


def clear_undo_record() -> None:
    if UNDO_FILE.is_file():
        UNDO_FILE.unlink()


def can_undo(record: UndoRecord | None = None) -> tuple[bool, str]:
    record = record or load_undo_record()
    if record is None:
        return False, "No completed run to undo."
    if record.relocated:
        if not record.backup or not record.backup.is_dir():
            return False, f"Backup missing: {record.backup_path}"
        if not record.project.is_dir():
            return False, f"Project folder missing: {record.project_path}"
        return True, f"Restore {record.backup.name} → {record.project.name}"
    if record.separate_target:
        target = Path(record.separate_target)
        if not target.is_dir():
            return False, f"Target folder missing: {target}"
        return True, f"Remove generated folder {target.name}"
    return False, "Nothing to undo for this run."


def undo_last_run(*, undo_github: bool = True) -> str:
    record = load_undo_record()
    ok, reason = can_undo(record)
    if not record or not ok:
        raise UndoError(reason)

    messages: list[str] = []

    if record.relocated:
        backup = record.backup
        project = record.project
        assert backup is not None
        generated_trash = project.parent / f"{project.name}.retro-git-trash"
        if generated_trash.exists():
            shutil.rmtree(generated_trash)
        if project.exists():
            console.print(f"[dim]Removing generated tree at {project}[/dim]")
            shutil.move(str(project), str(generated_trash))
        console.print(f"[dim]Restoring {backup} → {project}[/dim]")
        shutil.move(str(backup), str(project))
        messages.append(f"Restored local project at {project}")
        if generated_trash.exists():
            shutil.rmtree(generated_trash)
    elif record.separate_target:
        target = Path(record.separate_target)
        console.print(f"[dim]Removing {target}[/dim]")
        shutil.rmtree(target)
        messages.append(f"Removed {target}")

    if undo_github and record.published_github and record.github_owner and record.github_repo:
        console.print("[dim]Reverting GitHub repos…[/dim]")
        try:
            undo_github_publish(record.github_owner, record.github_repo)
            messages.append(
                f"GitHub: restored {record.github_owner}/{record.github_repo}"
            )
        except GitHubPublishError as exc:
            raise UndoError(
                f"Local undo OK, but GitHub revert failed: {exc}"
            ) from exc

    clear_undo_record()
    return "\n".join(messages)


def build_undo_record(
    *,
    layout_target: Path,
    backup_path: Path | None,
    relocated: bool,
    publish_github: bool,
    backup_for_github: Path | None,
) -> UndoRecord:
    owner: str | None = None
    repo: str | None = layout_target.name
    if publish_github:
        from retro_git.github_publish import parse_github_remote

        if backup_for_github and backup_for_github.is_dir():
            parsed = parse_github_remote(backup_for_github)
            if parsed:
                owner, _ = parsed
        if owner is None:
            try:
                owner = default_github_owner()
            except GitHubPublishError:
                owner = None

    return UndoRecord(
        project_path=str(layout_target),
        backup_path=str(backup_path) if backup_path else None,
        relocated=relocated,
        separate_target=None if relocated else str(layout_target),
        published_github=publish_github,
        github_owner=owner,
        github_repo=repo if publish_github else None,
    )
