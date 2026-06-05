from pathlib import Path

from git import Repo

from retro_git.config import Settings
from retro_git.executor.build_executor import BuildExecutor
from retro_git.models import CommitStep, DevelopmentPlan
from retro_git.planner.build_validator import validate_build_plan
from retro_git.planner.evolution import build_evolution_plan
from retro_git.scanner.manifest import build_manifest

_SETTINGS = Settings(author_name="Test", author_email="test@example.com")


def _make_source(tmp_path: Path) -> Path:
    src = tmp_path / "proj"
    src.mkdir()
    body = "\n".join(f"def func_{i}():\n    return {i}" for i in range(30)) + "\n"
    (src / "module.py").write_text(body, encoding="utf-8")
    (src / "README.md").write_text("# Title\n\nHello\n", encoding="utf-8")
    (src / "notes.txt").write_text("notes\n", encoding="utf-8")
    return src


def test_build_executor_history_and_final_tree(tmp_path: Path) -> None:
    src = _make_source(tmp_path)
    target = tmp_path / "out"
    manifest = build_manifest(src)
    plan = DevelopmentPlan(
        project_summary="t",
        detected_stack=[],
        commits=[
            CommitStep(order=1, message="docs: readme", files=["README.md"]),
            CommitStep(order=2, message="feat: module", files=["module.py"]),
            CommitStep(order=3, message="chore: notes", files=["notes.txt"]),
        ],
    )
    build_plan = build_evolution_plan(plan, manifest, src)
    validate_build_plan(build_plan, manifest, src)

    executor = BuildExecutor(src, target, settings=_SETTINGS)
    results = executor.run_plan(build_plan.steps, history_days=10)

    repo = Repo(target)
    assert len(list(repo.iter_commits())) == len(build_plan.steps)
    assert len(results) == len(build_plan.steps)

    assert (target / "module.py").read_text(encoding="utf-8") == (
        src / "module.py"
    ).read_text(encoding="utf-8")
    assert (target / "README.md").read_text(encoding="utf-8") == (
        src / "README.md"
    ).read_text(encoding="utf-8")


def test_build_executor_first_chunk_is_real_source(tmp_path: Path) -> None:
    src = _make_source(tmp_path)
    target = tmp_path / "out"
    manifest = build_manifest(src)
    plan = DevelopmentPlan(
        project_summary="t",
        detected_stack=[],
        commits=[
            CommitStep(order=1, message="feat: module", files=["module.py"]),
            CommitStep(order=2, message="docs: readme", files=["README.md"]),
            CommitStep(order=3, message="chore: notes", files=["notes.txt"]),
        ],
    )
    build_plan = build_evolution_plan(plan, manifest, src)
    validate_build_plan(build_plan, manifest, src)

    executor = BuildExecutor(src, target, settings=_SETTINGS)
    executor.run_plan(build_plan.steps, history_days=10)

    repo = Repo(target)
    commits = list(repo.iter_commits())  # newest first
    first_commit = commits[-1]
    first_blob = (first_commit.tree / "module.py").data_stream.read().decode("utf-8")
    final_module = (src / "module.py").read_text(encoding="utf-8")

    assert "def func_" in first_blob
    assert "TODO" not in first_blob
    assert "work in progress" not in first_blob.lower()
    assert first_blob in final_module or final_module.startswith(first_blob.strip())
    assert len(first_blob.splitlines()) < len(final_module.splitlines())


def test_build_executor_history_includes_deletions(tmp_path: Path) -> None:
    src = _make_source(tmp_path)
    target = tmp_path / "out"
    manifest = build_manifest(src)
    plan = DevelopmentPlan(
        project_summary="t",
        detected_stack=[],
        commits=[
            CommitStep(order=1, message="feat: module", files=["module.py"]),
            CommitStep(order=2, message="docs: readme", files=["README.md"]),
            CommitStep(order=3, message="chore: notes", files=["notes.txt"]),
        ],
    )
    build_plan = build_evolution_plan(plan, manifest, src)
    validate_build_plan(build_plan, manifest, src)

    executor = BuildExecutor(src, target, settings=_SETTINGS)
    executor.run_plan(build_plan.steps, history_days=10)

    repo = Repo(target)
    deletions = [
        c.stats.total["deletions"]
        for c in repo.iter_commits()
        if c.stats.total["deletions"] > 0
    ]
    assert deletions, "expected at least one commit with line deletions"


def test_build_executor_mixed_diffs_in_one_commit(tmp_path: Path) -> None:
    src = _make_source(tmp_path)
    target = tmp_path / "out"
    manifest = build_manifest(src)
    plan = DevelopmentPlan(
        project_summary="t",
        detected_stack=[],
        commits=[
            CommitStep(order=1, message="feat: module", files=["module.py"]),
            CommitStep(order=2, message="docs: readme", files=["README.md"]),
            CommitStep(order=3, message="chore: notes", files=["notes.txt"]),
        ],
    )
    build_plan = build_evolution_plan(plan, manifest, src)
    validate_build_plan(build_plan, manifest, src)

    executor = BuildExecutor(src, target, settings=_SETTINGS)
    executor.run_plan(build_plan.steps, history_days=10)

    repo = Repo(target)
    mixed = [
        c
        for c in repo.iter_commits()
        if c.stats.total["insertions"] > 0 and c.stats.total["deletions"] > 0
    ]
    assert mixed, "expected at least one commit with both insertions and deletions"
