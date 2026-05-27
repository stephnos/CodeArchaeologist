from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from git import Actor, Repo

from retro_git.config import Settings, load_settings
from retro_git.executor.file_stager import stage_files
from retro_git.models import CommitStep, Manifest
from retro_git.planner.plan_validator import expand_commit_files


class CommitExecutor:
    def __init__(
        self,
        source: Path,
        target: Path,
        manifest: Manifest,
        settings: Settings | None = None,
    ) -> None:
        self.source = source.resolve()
        self.target = target.resolve()
        self.manifest = manifest
        self.settings = settings or load_settings()
        self._manifest_paths = set(manifest.paths())
        self._repo: Repo | None = None

    @property
    def repo(self) -> Repo:
        if self._repo is None:
            if (self.target / ".git").exists():
                self._repo = Repo(self.target)
            else:
                self.target.mkdir(parents=True, exist_ok=True)
                self._repo = Repo.init(self.target)
        return self._repo

    def commit_step(
        self,
        step: CommitStep,
        *,
        commit_date: datetime | None = None,
    ) -> str:
        paths = sorted(expand_commit_files(step.files, self._manifest_paths))
        stage_files(self.source, self.target, paths)

        repo = self.repo
        repo.index.add(paths)
        author = Actor(self.settings.author_name, self.settings.author_email)
        when = commit_date or datetime.now(timezone.utc)
        hexsha = repo.index.commit(
            step.message,
            author=author,
            committer=author,
            author_date=when,
            commit_date=when,
        )
        return hexsha.hexsha

    def run_plan(
        self,
        steps: list[CommitStep],
        *,
        history_days: int,
    ) -> list[tuple[CommitStep, str]]:
        if not steps:
            return []

        end = datetime.now(timezone.utc)
        start = end - timedelta(days=max(1, history_days))
        n = len(steps)
        results: list[tuple[CommitStep, str]] = []

        for i, step in enumerate(steps):
            if n == 1:
                when = end
            else:
                fraction = i / (n - 1)
                when = start + (end - start) * fraction
            sha = self.commit_step(step, commit_date=when)
            results.append((step, sha))
        return results

    def commit_all(
        self,
        paths: list[str],
        message: str,
        *,
        commit_date: datetime | None = None,
    ) -> str:
        stage_files(self.source, self.target, paths)
        repo = self.repo
        repo.index.add(paths)
        author = Actor(self.settings.author_name, self.settings.author_email)
        when = commit_date or datetime.now(timezone.utc)
        hexsha = repo.index.commit(
            message,
            author=author,
            committer=author,
            author_date=when,
            commit_date=when,
        )
        return hexsha.hexsha
