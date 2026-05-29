from __future__ import annotations

import json
import shutil
from enum import Enum
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from retro_git.config import load_settings
from retro_git.executor.commit_executor import CommitExecutor
from retro_git.llm.provider import OllamaProvider, get_provider
from retro_git.models import DevelopmentPlan
from retro_git.planner.commit_bounds import enforce_commit_bounds
from retro_git.planner.plan_normalizer import normalize_plan
from retro_git.planner.plan_repair import repair_plan
from retro_git.planner.plan_validator import validate_plan
from retro_git.scanner.file_collection import is_git_repository
from retro_git.scanner.manifest import build_manifest, save_manifest_cache
from retro_git.github_publish import GitHubPublishError, publish_replacing_old
from retro_git.layout import apply_relocate, old_workspaces_root, resolve_layout
from retro_git.undo import UndoError, build_undo_record, save_undo_record, undo_last_run
from retro_git.verify.fix_commit import verify_and_fix
from retro_git.verify.tree_comparator import compare_trees

app = typer.Typer(
    name="retro-git",
    help="Generate realistic Git commit history from a finished codebase.",
    invoke_without_command=True,
)
console = Console()


@app.callback()
def main(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is not None:
        return
    from retro_git.gui import launch_gui

    launch_gui()
    raise typer.Exit()


class ProviderChoice(str, Enum):
    ollama = "ollama"
    groq = "groq"
    heuristic = "heuristic"


def _ensure_empty_target(target: Path, force: bool) -> None:
    if not target.exists():
        return
    if target.is_dir() and not any(target.iterdir()):
        return
    if force:
        for child in target.iterdir():
            if child.name == ".git":
                shutil.rmtree(child)
            elif child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
        return
    raise typer.BadParameter(
        f"target directory is not empty: {target}. Use --force to clear it."
    )


def _resolve_provider(choice: ProviderChoice) -> ProviderChoice:
    if choice != ProviderChoice.ollama:
        return choice
    settings = load_settings()
    ollama = OllamaProvider(settings)
    if ollama.check_available():
        return ProviderChoice.ollama
    if settings.groq_api_key:
        console.print(
            "[yellow]Ollama not reachable; falling back to Groq (free tier).[/yellow]"
        )
        return ProviderChoice.groq
    console.print(
        "[yellow]Ollama not reachable; using heuristic planner (no API).[/yellow]\n"
        "  Install Ollama for LLM plans: https://ollama.com\n"
        "  Or set GROQ_API_KEY for cloud free tier.\n"
        "  Or pass --provider heuristic explicitly."
    )
    return ProviderChoice.heuristic


def _print_plan_table(plan: DevelopmentPlan) -> None:
    table = Table(title="Development plan")
    table.add_column("#", style="cyan")
    table.add_column("Message")
    table.add_column("Files", justify="right")
    for step in plan.commits:
        table.add_row(str(step.order), step.message, str(len(step.files)))
    console.print(table)
    if plan.project_summary:
        console.print(f"\n[dim]{plan.project_summary}[/dim]")


def _save_plan_cache(target: Path, plan: DevelopmentPlan) -> None:
    cache = target / ".retro-git"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "plan.json").write_text(
        plan.model_dump_json(indent=2),
        encoding="utf-8",
    )


@app.command("gui")
def gui_cmd() -> None:
    """Open the graphical form."""
    from retro_git.gui import launch_gui

    launch_gui()


@app.command("generate")
def generate(
    source: Path = typer.Option(..., "--source", "-s", help="Finished project directory"),
    target: Optional[Path] = typer.Option(
        None,
        "--target",
        "-t",
        help="Output directory (blank = replace source; backup → old/<name>.old)",
    ),
    provider: ProviderChoice = typer.Option(
        ProviderChoice.ollama,
        "--provider",
        "-p",
        help="LLM provider (ollama=free local default)",
    ),
    min_commits: int = typer.Option(3, "--min-commits", help="Minimum commits in plan"),
    max_commits: int = typer.Option(20, "--max-commits", help="Maximum commits in plan"),
    history_days: int = typer.Option(
        14,
        "--history-days",
        "-d",
        help="Spread commit timestamps over this many days",
    ),
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Fail on verification mismatch instead of auto fix commit",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Plan only; no git writes"),
    force: bool = typer.Option(False, "--force", help="Clear non-git files in target"),
    include_secrets: bool = typer.Option(
        False,
        "--include-secrets",
        help="Include .env files in manifest",
    ),
    include_untracked: bool = typer.Option(
        False,
        "--include-untracked",
        help="Include untracked files (git repos default to tracked files only)",
    ),
    publish_github: bool = typer.Option(
        True,
        "--publish-github/--no-publish-github",
        help="Rename old repo to <name>.old (private), create <name> (public), and push",
    ),
    github_private: bool = typer.Option(
        False,
        "--github-private/--github-public",
        help="Visibility for the new GitHub repo",
    ),
) -> None:
    """Scan source, plan commits, build git history in target."""
    layout, layout_err = resolve_layout(str(source), str(target) if target else "")
    if layout_err or layout is None:
        raise typer.BadParameter(layout_err or "invalid paths")

    if min_commits < 1 or max_commits < min_commits:
        raise typer.BadParameter("invalid --min-commits / --max-commits")

    if layout.relocate_to_old and force:
        raise typer.BadParameter("--force is not used when target is blank (relocate mode).")

    console.print(f"[bold]Scanning[/bold] {layout.scan_root}")
    if is_git_repository(layout.scan_root) and not include_untracked:
        console.print("  [dim]Git repo: using tracked files only (ignores local build artifacts)[/dim]")
    manifest = build_manifest(
        layout.scan_root,
        include_secrets=include_secrets,
        include_untracked=include_untracked,
    )
    if not manifest.files:
        raise typer.BadParameter(f"no files found under {layout.scan_root}")

    staging_source = layout.staging_source
    target = layout.target
    backup_path: Path | None = None

    if not dry_run and not layout.relocate_to_old:
        _ensure_empty_target(target, force)

    console.print(
        f"  {len(manifest.files)} files, {manifest.total_bytes:,} bytes"
    )
    if manifest.stack_hints:
        console.print(f"  stack: {', '.join(manifest.stack_hints)}")

    resolved = _resolve_provider(provider)
    llm = get_provider(resolved.value)  # type: ignore[arg-type]

    console.print(f"\n[bold]Planning[/bold] via {resolved.value}...")
    try:
        plan = llm.generate_plan(
            manifest,
            min_commits=min_commits,
            max_commits=max_commits,
        )
    except Exception as exc:
        if resolved == ProviderChoice.heuristic:
            console.print(f"[red]Planning failed:[/red] {exc}")
            raise typer.Exit(code=1) from exc
        console.print(f"[yellow]Planning failed ({exc})[/yellow]")
        console.print("[dim]Falling back to heuristic planner…[/dim]")
        plan = get_provider("heuristic").generate_plan(
            manifest,
            min_commits=min_commits,
            max_commits=max_commits,
        )

    plan = normalize_plan(plan)
    try:
        validate_plan(plan, manifest)
    except ValueError as exc:
        console.print(f"[yellow]Invalid plan from provider:[/yellow] {exc}")
        console.print("[dim]Attempting automatic plan repair...[/dim]")
        repaired = normalize_plan(repair_plan(plan, manifest))
        try:
            validate_plan(repaired, manifest)
            plan = repaired
            console.print("[green]Plan repaired successfully.[/green]")
            if not dry_run:
                cache = target / ".retro-git"
                cache.mkdir(parents=True, exist_ok=True)
                (cache / "repaired-plan.json").write_text(
                    plan.model_dump_json(indent=2),
                    encoding="utf-8",
                )
        except ValueError as repair_exc:
            console.print(f"[red]Invalid plan after repair:[/red] {repair_exc}")
            if not dry_run:
                cache = target / ".retro-git"
                cache.mkdir(parents=True, exist_ok=True)
                (cache / "invalid-plan.json").write_text(
                    plan.model_dump_json(indent=2),
                    encoding="utf-8",
                )
            raise typer.Exit(code=1) from repair_exc

    adjusted = enforce_commit_bounds(
        plan,
        min_commits=min_commits,
        max_commits=max_commits,
        file_count=len(manifest.files),
    )
    if len(adjusted.commits) != len(plan.commits):
        console.print(
            f"[dim]Adjusted plan to {len(adjusted.commits)} commits "
            f"(requested {min_commits}-{max_commits}).[/dim]"
        )
    plan = adjusted
    validate_plan(plan, manifest)

    _print_plan_table(plan)

    if dry_run:
        console.print("\n[green]Dry run complete[/green] (no commits written).")
        raise typer.Exit()

    if layout.relocate_to_old:
        staging_source = apply_relocate(layout)
        console.print(
            f"[dim]Moved {layout.scan_root.name} → {Path(staging_source).name}[/dim]"
        )
        backup_path = staging_source
        target = layout.target

    save_manifest_cache(target, manifest)
    _save_plan_cache(target, plan)

    executor = CommitExecutor(staging_source, target, manifest)
    console.print(f"\n[bold]Executing[/bold] {len(plan.commits)} commits...")
    results = executor.run_plan(plan.commits, history_days=history_days)
    for step, sha in results:
        console.print(f"  [cyan]{step.order:02d}[/cyan] {sha[:7]}  {step.message}")

    console.print("\n[bold]Verifying[/bold] tree against source...")
    diff, fix_sha = verify_and_fix(
        staging_source,
        target,
        executor,
        manifest,
        strict=strict,
        include_secrets=include_secrets,
        include_untracked=include_untracked,
    )

    if diff.ok:
        console.print("[green]Verification passed[/green] — target matches source.")
    elif strict:
        _print_diff(diff)
        console.print("[red]Verification failed[/red] (--strict; no fix commit).")
        raise typer.Exit(code=1)
    elif fix_sha:
        console.print(f"[yellow]Fix commit[/yellow] {fix_sha[:7]}  chore: sync...")
        after = compare_trees(
            staging_source,
            target,
            paths=manifest.paths(),
            include_secrets=include_secrets,
            include_untracked=include_untracked,
        )
        if after.ok:
            console.print("[green]Verification passed after fix commit.[/green]")
        else:
            _print_diff(after)
            console.print("[red]Still mismatched after fix commit.[/red]")
            raise typer.Exit(code=1)
    else:
        _print_diff(diff)
        raise typer.Exit(code=1)

    console.print(f"\n[bold]Done.[/bold] Repository: {target}")
    if backup_path:
        console.print(f"[dim]Original project backup:[/dim] {backup_path}")

    published = False
    if publish_github and not dry_run:
        console.print("\n[bold]Publishing to GitHub…[/bold]")
        try:
            url = publish_replacing_old(
                target,
                backup_path,
                private=github_private,
            )
            console.print(f"[bold]GitHub:[/bold] {url}")
            published = True
        except GitHubPublishError as exc:
            console.print(f"[red]GitHub publish failed:[/red] {exc}")
            raise typer.Exit(code=1) from exc

    if not dry_run:
        save_undo_record(
            build_undo_record(
                layout_target=target,
                backup_path=backup_path,
                relocated=layout.relocate_to_old,
                publish_github=published,
                backup_for_github=backup_path,
            )
        )
        console.print("[dim]Undo snapshot saved (retro-git undo).[/dim]")


def _print_diff(diff) -> None:
    if diff.missing_in_target:
        console.print(f"  missing: {len(diff.missing_in_target)}")
        for p in diff.missing_in_target[:10]:
            console.print(f"    - {p}")
    if diff.content_mismatch:
        console.print(f"  changed: {len(diff.content_mismatch)}")
        for p in diff.content_mismatch[:10]:
            console.print(f"    ~ {p}")
    if diff.extra_in_target:
        console.print(f"  extra: {len(diff.extra_in_target)}")
        for p in diff.extra_in_target[:10]:
            console.print(f"    + {p}")


@app.command("undo")
def undo_cmd(
    undo_github: bool = typer.Option(
        True,
        "--github/--no-github",
        help="Also revert GitHub (delete new repo, restore .old name)",
    ),
) -> None:
    """Undo the last generate run (restore <name>.old, revert GitHub)."""
    try:
        summary = undo_last_run(undo_github=undo_github)
        console.print(f"[green]Undo complete.[/green]\n{summary}")
    except UndoError as exc:
        console.print(f"[red]Undo failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc


@app.command("publish-github")
def publish_github_cmd(
    target: Path = typer.Argument(
        ...,
        help="Local folder with generated git history to push",
    ),
    backup: Optional[Path] = typer.Option(
        None,
        "--backup",
        help="Path to <name>.old backup (for detecting GitHub owner/repo)",
    ),
    github_private: bool = typer.Option(
        False,
        "--github-private/--github-public",
    ),
) -> None:
    """Create GitHub repo (renaming any existing one to .old) and push target."""
    target = target.resolve()
    backup = backup.resolve() if backup else (old_workspaces_root() / f"{target.name}.old")
    if not backup.is_dir():
        backup = None
    try:
        url = publish_replacing_old(target, backup, private=github_private)
        console.print(f"[bold]GitHub:[/bold] {url}")
    except GitHubPublishError as exc:
        console.print(f"[red]GitHub publish failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc


@app.command("verify")
def verify(
    source: Path = typer.Option(..., "--source", "-s"),
    target: Path = typer.Option(..., "--target", "-t"),
) -> None:
    """Compare target working tree to source (ignores .git and .retro-git)."""
    diff = compare_trees(source.resolve(), target.resolve())
    if diff.ok:
        console.print("[green]Trees match.[/green]")
        raise typer.Exit()
    _print_diff(diff)
    raise typer.Exit(code=1)


@app.command("plan-export")
def plan_export(
    source: Path = typer.Option(..., "--source", "-s"),
    output: Path = typer.Option(..., "--output", "-o"),
    provider: ProviderChoice = typer.Option(ProviderChoice.heuristic, "--provider", "-p"),
    min_commits: int = typer.Option(3, "--min-commits"),
    max_commits: int = typer.Option(20, "--max-commits"),
) -> None:
    """Write plan JSON only (no git operations)."""
    manifest = build_manifest(source.resolve())
    resolved = _resolve_provider(provider)
    plan = normalize_plan(
        get_provider(resolved.value).generate_plan(  # type: ignore[arg-type]
            manifest,
            min_commits=min_commits,
            max_commits=max_commits,
        )
    )
    validate_plan(plan, manifest)
    output.write_text(
        json.dumps(json.loads(plan.model_dump_json()), indent=2),
        encoding="utf-8",
    )
    console.print(f"Wrote {output}")


if __name__ == "__main__":
    app()
