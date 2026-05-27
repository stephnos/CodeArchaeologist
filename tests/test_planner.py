from pathlib import Path

import pytest

from retro_git.planner.heuristic_planner import HeuristicPlanner
from retro_git.planner.plan_normalizer import normalize_plan
from retro_git.planner.plan_validator import validate_plan
from retro_git.scanner.manifest import build_manifest

FIXTURE = Path(__file__).parent / "fixtures" / "sample_app"


def test_heuristic_plan_covers_all_files() -> None:
    manifest = build_manifest(FIXTURE)
    planner = HeuristicPlanner()
    plan = normalize_plan(
        planner.generate_plan(manifest, min_commits=2, max_commits=20)
    )
    validate_plan(plan, manifest)
    covered: set[str] = set()
    for step in plan.commits:
        covered.update(step.files)
    assert covered == set(manifest.paths())
