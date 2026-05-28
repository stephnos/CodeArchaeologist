from pathlib import Path

from retro_git.models import CommitStep, DevelopmentPlan
from retro_git.planner.plan_repair import repair_plan
from retro_git.planner.plan_validator import validate_plan
from retro_git.scanner.manifest import build_manifest

FIXTURE = Path(__file__).parent / "fixtures" / "sample_app"


def test_repair_plan_handles_unknown_and_missing_paths() -> None:
    manifest = build_manifest(FIXTURE)
    plan = DevelopmentPlan(
        project_summary="bad llm output",
        detected_stack=["python"],
        commits=[
            CommitStep(
                order=1,
                message="chore: init",
                files=["pyproject.toml", "Dockerfile"],
            ),
            CommitStep(
                order=2,
                message="feat: app",
                files=["src/"],
            ),
        ],
    )

    repaired = repair_plan(plan, manifest)
    validate_plan(repaired, manifest)
    covered: set[str] = set()
    for step in repaired.commits:
        covered.update(step.files)
    assert covered == set(manifest.paths())
