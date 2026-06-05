from __future__ import annotations

import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from git import Actor, Repo

from retro_git.config import Settings, load_settings
from retro_git.models import BuildStep, FileEdit, LineRange
from retro_git.textfiles import read_text_lines


class BuildExecutor:
    """Executes a v2 BuildPlan, reconstructing partial file states per commit."""

    def __init__(
        self,
        source: Path,
        target: Path,
        settings: Settings | None = None,
    ) -> None:
        self.source = source.resolve()
        self.target = target.resolve()
        self.settings = settings or load_settings()
        self._repo: Repo | None = None
        self._lines_cache: dict[str, list[str] | None] = {}
        self._present: dict[str, list[LineRange]] = {}

    @property
    def repo(self) -> Repo:
        if self._repo is None:
            if (self.target / ".git").exists():
                self._repo = Repo(self.target)
            else:
                self.target.mkdir(parents=True, exist_ok=True)
                self._repo = Repo.init(self.target)
        return self._repo

    def _source_lines(self, rel: str) -> list[str] | None:
        if rel not in self._lines_cache:
            self._lines_cache[rel] = read_text_lines(self.source / rel)
        return self._lines_cache[rel]

    def _render_text_content(self, rel: str) -> str:
        lines = self._source_lines(rel)
        if lines is None:
            return ""
        present = self._present.get(rel, [])
        indices = sorted({i for rng in present for i in rng.indices()})
        return "".join(lines[i] for i in indices)

    def _write_file(self, edit: FileEdit) -> None:
        rel = edit.path.replace("\\", "/")
        dst = self.target / rel
        dst.parent.mkdir(parents=True, exist_ok=True)

        if edit.whole:
            shutil.copy2(self.source / rel, dst)
            return

        lines = self._source_lines(rel)
        if lines is None:
            shutil.copy2(self.source / rel, dst)
            return

        if edit.mode == "reset":
            self._present[rel] = list(edit.ranges)
        else:
            present = self._present.setdefault(rel, [])
            present.extend(edit.ranges)
        dst.write_text(self._render_text_content(rel), encoding="utf-8", newline="")

    def commit_step(self, step: BuildStep, *, commit_date: datetime | None = None) -> str:
        changed: list[str] = []
        for edit in step.edits:
            self._write_file(edit)
            changed.append(edit.path.replace("\\", "/"))

        repo = self.repo
        repo.index.add(changed)
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
        steps: list[BuildStep],
        *,
        history_days: int,
    ) -> list[tuple[BuildStep, str]]:
        if not steps:
            return []

        end = datetime.now(timezone.utc)
        start = end - timedelta(days=max(1, history_days))
        n = len(steps)
        results: list[tuple[BuildStep, str]] = []

        for i, step in enumerate(steps):
            when = end if n == 1 else start + (end - start) * (i / (n - 1))
            sha = self.commit_step(step, commit_date=when)
            results.append((step, sha))
        return results
