"""Rule-based planner (no API). Useful when Ollama is unavailable or for tests."""

from __future__ import annotations

from retro_git.llm.provider import LLMProvider
from retro_git.models import CommitStep, DevelopmentPlan, Manifest

_PRIORITY_PREFIXES: list[tuple[str, str]] = [
    (".github/", "ci: add GitHub Actions workflows"),
    ("docker", "build: add container configuration"),
    ("Dockerfile", "build: add Dockerfile"),
    ("pyproject.toml", "chore: initialize Python project"),
    ("package.json", "chore: initialize Node.js project"),
    ("requirements", "chore: add Python dependencies"),
    (".gitignore", "chore: add gitignore"),
    ("README", "docs: add project README"),
    ("LICENSE", "chore: add license"),
    ("alembic/", "feat(db): add database migrations"),
    ("migrations/", "feat(db): add database migrations"),
    ("models/", "feat: add data models"),
    ("schemas/", "feat: add request/response schemas"),
    ("utils/", "feat: add shared utilities"),
    ("lib/", "feat: add shared library code"),
    ("services/", "feat: implement domain services"),
    ("api/", "feat(api): add API routes"),
    ("routes/", "feat(api): add routes"),
    ("middleware/", "feat: add middleware"),
    ("tests/", "test: add test suite"),
    ("static/", "style: add static assets"),
    ("assets/", "style: add assets"),
    ("src/components/", "feat(ui): add UI components"),
    ("components/", "feat(ui): add components"),
    ("pages/", "feat(ui): add pages"),
]


def _score_path(path: str) -> tuple[int, str]:
    lower = path.lower()
    for idx, (prefix, _) in enumerate(_PRIORITY_PREFIXES):
        if lower.startswith(prefix.lower()) or prefix.lower() in lower:
            return idx, path
    if path.endswith((".md", ".rst")):
        return 50, path
    if path.endswith((".css", ".scss", ".sass")):
        return 45, path
    if path.endswith((".html", ".tsx", ".jsx", ".vue")):
        return 40, path
    if "test" in lower:
        return 35, path
    if path.endswith(".py"):
        return 20, path
    return 30, path


def _message_for_group(paths: list[str]) -> str:
    if len(paths) == 1:
        name = paths[0].split("/")[-1]
        return f"feat: add {name}"
    first = paths[0]
    for prefix, msg in _PRIORITY_PREFIXES:
        if first.startswith(prefix) or prefix.rstrip("/") in first:
            return msg
    folder = first.split("/")[0] if "/" in first else "module"
    return f"feat: add {folder} files"


class HeuristicPlanner(LLMProvider):
    def generate_plan(
        self,
        manifest: Manifest,
        *,
        min_commits: int,
        max_commits: int,
    ) -> DevelopmentPlan:
        paths = sorted(manifest.paths(), key=lambda p: _score_path(p))
        if not paths:
            raise ValueError("empty manifest")

        target_commits = max(
            min_commits,
            min(max_commits, max(3, len(paths) // 8)),
        )
        batch_size = max(1, (len(paths) + target_commits - 1) // target_commits)

        commits: list[CommitStep] = []
        order = 1
        for i in range(0, len(paths), batch_size):
            batch = paths[i : i + batch_size]
            commits.append(
                CommitStep(
                    order=order,
                    message=_message_for_group(batch),
                    intent="Heuristic batch by path priority",
                    files=batch,
                )
            )
            order += 1

        return DevelopmentPlan(
            project_summary="Heuristic development plan (no LLM)",
            detected_stack=manifest.stack_hints,
            commits=commits,
        )
