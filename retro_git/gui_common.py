from __future__ import annotations

from pathlib import Path

import typer

from retro_git.cli import ProviderChoice, generate
from retro_git.layout import old_workspaces_root, resolve_layout
from retro_git.undo import UndoError, can_undo, undo_last_run


def run_generate_job(
    source: Path,
    target: Path,
    *,
    force: bool,
    relocate_to_old: bool,
    provider: ProviderChoice,
    history_days: int,
    min_commits: int,
    max_commits: int,
    dry_run: bool,
    strict: bool,
    include_secrets: bool,
    publish_github: bool,
    github_private: bool,
) -> tuple[int, str]:
    """Run generate; return (exit_code, user-facing message)."""
    target_arg = "" if relocate_to_old else str(target)
    try:
        generate(
            source=source,
            target=Path(target_arg) if target_arg else None,
            provider=provider,
            min_commits=min_commits,
            max_commits=max_commits,
            history_days=history_days,
            strict=strict,
            dry_run=dry_run,
            force=force,
            include_secrets=include_secrets,
            publish_github=publish_github,
            github_private=github_private,
        )
    except typer.Exit as exc:
        code = int(exc.exit_code or 0)
        if code == 0:
            if dry_run:
                return 0, "Dry run finished — see the terminal for the plan."
            msg = f"Done. Local repo: {source if relocate_to_old else target}"
            if relocate_to_old:
                msg += f"\nBackup: {old_workspaces_root() / (source.name + '.old')}"
            msg += "\nUndo available (use Undo button or: retro-git undo)"
            return 0, msg
        return code, "Finished with errors — see the terminal."
    except typer.BadParameter as exc:
        return 1, str(exc)
    except Exception as exc:
        return 1, str(exc)
    return 0, f"Done. Repository: {target}"


def run_undo_job(*, undo_github: bool = True) -> tuple[int, str]:
    try:
        summary = undo_last_run(undo_github=undo_github)
        return 0, f"Undo complete.\n{summary}"
    except UndoError as exc:
        return 1, str(exc)


def resolve_paths(
    source_text: str, target_text: str
) -> tuple[Path, Path, bool, bool, str | None]:
    """Return (scan_root, target, force, relocate_to_old, error)."""
    layout, err = resolve_layout(source_text, target_text)
    if err or layout is None:
        return Path(), Path(), False, False, err
    return (
        layout.scan_root,
        layout.target,
        layout.force,
        layout.relocate_to_old,
        None,
    )


def undo_status_message() -> tuple[bool, str]:
    return can_undo()
