from pathlib import Path

from retro_git.models import CommitStep, DevelopmentPlan
from retro_git.planner.build_validator import validate_build_plan
from retro_git.planner.evolution import build_evolution_plan, message_for_extension
from retro_git.planner.semantic_split import semantic_split_ranges
from retro_git.scanner.manifest import build_manifest
from retro_git.textfiles import read_text_lines


def _make_source(tmp_path: Path) -> Path:
    src = tmp_path / "proj"
    src.mkdir()
    long_py = "\n".join(
        [f"def func_{i}():" + "\n    return " + str(i) for i in range(40)]
    )
    (src / "big.py").write_text(long_py + "\n", encoding="utf-8")
    (src / "tiny.py").write_text("x = 1\n", encoding="utf-8")
    (src / "logo.bin").write_bytes(bytes(range(256)))
    return src


def test_semantic_split_partitions_exactly() -> None:
    lines = [f"def func_{i}():\n    return {i}\n" for i in range(20)]
    ranges = semantic_split_ranges(lines, "mod.py", 4)
    assert ranges[0][0] == 0
    assert ranges[-1][1] == len(lines)
    covered: list[int] = []
    for start, end in ranges:
        covered.extend(range(start, end))
    assert covered == list(range(len(lines)))


def test_evolution_plan_reconstructs_source(tmp_path: Path) -> None:
    src = _make_source(tmp_path)
    manifest = build_manifest(src)
    plan = DevelopmentPlan(
        project_summary="t",
        detected_stack=[],
        commits=[
            CommitStep(order=1, message="feat: big", files=["big.py"]),
            CommitStep(order=2, message="chore: tiny", files=["tiny.py"]),
            CommitStep(order=3, message="chore: assets", files=["logo.bin"]),
        ],
    )
    build_plan = build_evolution_plan(plan, manifest, src)
    validate_build_plan(build_plan, manifest, src)

    big_commits = [
        s.order for s in build_plan.steps if any(e.path == "big.py" for e in s.edits)
    ]
    assert len(big_commits) >= 2

    from retro_git.planner.build_validator import _simulate_present

    lines = read_text_lines(src / "big.py")
    assert lines is not None
    all_edits = [e for s in build_plan.steps for e in s.edits if e.path == "big.py"]
    present = _simulate_present(all_edits)
    rebuilt = "".join(lines[i] for i in sorted(present["big.py"]))
    assert rebuilt == (src / "big.py").read_text(encoding="utf-8")


def test_no_scaffold_or_wip_text(tmp_path: Path) -> None:
    src = _make_source(tmp_path)
    manifest = build_manifest(src)
    plan = DevelopmentPlan(
        project_summary="t",
        detected_stack=[],
        commits=[
            CommitStep(order=1, message="feat: big", files=["big.py"]),
            CommitStep(order=2, message="chore: tiny", files=["tiny.py"]),
            CommitStep(order=3, message="chore: assets", files=["logo.bin"]),
        ],
    )
    build_plan = build_evolution_plan(plan, manifest, src)
    for step in build_plan.steps:
        for edit in step.edits:
            assert not getattr(edit, "scaffold", False)
        assert "TODO" not in step.message
        assert "work in progress" not in step.message.lower()
        assert "extend implementation" not in step.message.lower()
        assert "; feat(" not in step.message


def test_extension_messages_use_add(tmp_path: Path) -> None:
    lines = ["fn parse() {\n", "    todo!()\n", "}\n", "\n", "fn render() {\n", "}\n"]
    msg = message_for_extension("src/parser.rs", lines, [(0, 3)])
    assert msg == "feat(src): add parse"


def test_binary_marked_whole(tmp_path: Path) -> None:
    src = _make_source(tmp_path)
    manifest = build_manifest(src)
    plan = DevelopmentPlan(
        project_summary="t",
        detected_stack=[],
        commits=[CommitStep(order=1, message="all", files=["big.py", "tiny.py", "logo.bin"])],
    )
    build_plan = build_evolution_plan(plan, manifest, src)
    whole = [e for s in build_plan.steps for e in s.edits if e.whole]
    assert any(e.path == "logo.bin" for e in whole)
