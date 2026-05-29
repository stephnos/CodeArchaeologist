from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from retro_git.executor.commit_executor import CommitExecutor
from retro_git.models import Manifest
from retro_git.verify.tree_comparator import TreeDiff, compare_trees

FIX_COMMIT_MESSAGE = "chore: sync generated history with source tree"


def apply_fix_commit(executor: CommitExecutor, diff: TreeDiff) -> str | None:
    paths = diff.all_paths_to_sync()
    if not paths:
        return None
    return executor.commit_all(
        paths,
        FIX_COMMIT_MESSAGE,
        commit_date=datetime.now(timezone.utc),
    )


def verify_and_fix(
    source: Path,
    target: Path,
    executor: CommitExecutor,
    manifest: Manifest,
    *,
    strict: bool,
    include_secrets: bool = False,
    include_untracked: bool = False,
) -> tuple[TreeDiff, str | None]:
    paths = manifest.paths()
    diff = compare_trees(
        source,
        target,
        paths=paths,
        include_secrets=include_secrets,
        include_untracked=include_untracked,
    )
    if diff.ok:
        return diff, None
    if strict:
        return diff, None
    fix_sha = apply_fix_commit(executor, diff)
    diff = compare_trees(
        source,
        target,
        paths=paths,
        include_secrets=include_secrets,
        include_untracked=include_untracked,
    )
    return diff, fix_sha
