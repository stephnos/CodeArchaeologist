from __future__ import annotations

import re
import subprocess
from pathlib import Path

from rich.console import Console

console = Console()


class GitHubPublishError(Exception):
    pass


def _run_gh(args: list[str], *, cwd: Path | None = None) -> str:
    result = subprocess.run(
        ["gh", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        raise GitHubPublishError(err or f"gh {' '.join(args)} failed")
    return (result.stdout or "").strip()


def gh_available() -> bool:
    try:
        subprocess.run(["gh", "--version"], capture_output=True, check=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def gh_authenticated() -> bool:
    if not gh_available():
        return False
    result = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True)
    return result.returncode == 0


def parse_github_remote(path: Path) -> tuple[str, str] | None:
    """Return (owner, repo) from origin URL if present."""
    if not (path / ".git").exists():
        return None
    result = subprocess.run(
        ["git", "-C", str(path), "config", "--get", "remote.origin.url"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    url = (result.stdout or "").strip()
    # https://github.com/owner/repo.git or git@github.com:owner/repo.git
    patterns = [
        r"github\.com[:/](?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            repo = match.group("repo").removesuffix(".git")
            return match.group("owner"), repo
    return None


def github_repo_exact_name(owner: str, repo: str) -> bool:
    """True only if owner/repo exists under that exact name (not a redirect alias)."""
    result = subprocess.run(
        ["gh", "repo", "view", f"{owner}/{repo}", "--json", "name", "-q", ".name"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False
    return (result.stdout or "").strip() == repo


def github_repo_exists(owner: str, repo: str) -> bool:
    return github_repo_exact_name(owner, repo)


def default_github_owner() -> str:
    return _run_gh(["api", "user", "-q", ".login"])


def rename_github_repo(owner: str, current_name: str, new_name: str) -> None:
    if current_name == new_name:
        return
    if github_repo_exact_name(owner, new_name):
        raise GitHubPublishError(
            f"GitHub repo {owner}/{new_name} already exists; "
            f"cannot rename {owner}/{current_name}."
        )
    _run_gh(["repo", "rename", new_name, "--repo", f"{owner}/{current_name}", "--yes"])
    console.print(f"[dim]Renamed GitHub repo {owner}/{current_name} → {owner}/{new_name}[/dim]")


def set_repo_visibility(owner: str, repo: str, *, private: bool) -> None:
    visibility = "private" if private else "public"
    _run_gh(
        [
            "repo",
            "edit",
            f"{owner}/{repo}",
            "--visibility",
            visibility,
            "--accept-visibility-change-consequences",
        ]
    )
    console.print(f"[dim]Set {owner}/{repo} visibility: {visibility}[/dim]")


def delete_github_repo(owner: str, repo: str) -> None:
    _run_gh(["repo", "delete", f"{owner}/{repo}", "--yes"])
    console.print(f"[dim]Deleted GitHub repo {owner}/{repo}[/dim]")


def create_github_repo_and_push(
    target: Path,
    *,
    owner: str,
    repo_name: str,
    private: bool = False,
) -> str:
    if not gh_authenticated():
        raise GitHubPublishError(
            "GitHub CLI is not logged in. Run: gh auth login"
        )
    visibility = "--private" if private else "--public"
    full_name = f"{owner}/{repo_name}"
    if github_repo_exists(owner, repo_name):
        raise GitHubPublishError(f"GitHub repo already exists: {full_name}")

    _run_gh(
        [
            "repo",
            "create",
            repo_name,
            visibility,
            f"--source={target.resolve()}",
            "--remote=origin",
            "--push",
        ],
    )
    url = _run_gh(["repo", "view", full_name, "--json", "url", "-q", ".url"])
    return url


def publish_replacing_old(
    target: Path,
    backup_path: Path | None,
    *,
    private: bool = False,
) -> str:
    """
    Rename existing GitHub repo <name> to <name>.old, then create and push <name>.
    """
    repo_name = target.name
    old_repo_name = f"{repo_name}.old"

    owner: str | None = None
    existing_repo: str | None = None
    if backup_path and backup_path.is_dir():
        parsed = parse_github_remote(backup_path)
        if parsed:
            owner, existing_repo = parsed
    if owner is None:
        owner = default_github_owner()
        existing_repo = repo_name

    if github_repo_exists(owner, old_repo_name):
        delete_github_repo(owner, old_repo_name)

    if existing_repo == repo_name and github_repo_exists(owner, repo_name):
        rename_github_repo(owner, repo_name, old_repo_name)
        set_repo_visibility(owner, old_repo_name, private=True)

    url = create_github_repo_and_push(
        target,
        owner=owner,
        repo_name=repo_name,
        private=private,
    )
    console.print(f"[green]Pushed to GitHub:[/green] {url}")
    return url


def undo_github_publish(owner: str, repo_name: str) -> None:
    """Delete the new repo and rename <name>.old back to <name>."""
    old_repo_name = f"{repo_name}.old"
    if github_repo_exact_name(owner, repo_name):
        _run_gh(["repo", "delete", f"{owner}/{repo_name}", "--yes"])
        console.print(f"[dim]Deleted GitHub repo {owner}/{repo_name}[/dim]")
    if github_repo_exact_name(owner, old_repo_name):
        rename_github_repo(owner, old_repo_name, repo_name)
        console.print(f"[dim]Restored GitHub repo {owner}/{repo_name}[/dim]")
