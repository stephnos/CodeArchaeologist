from retro_git.models import CommitStep, DevelopmentPlan
from retro_git.planner.commit_bounds import enforce_commit_bounds


def _plan_with_counts(*counts: int) -> DevelopmentPlan:
    commits: list[CommitStep] = []
    file_num = 0
    for idx, count in enumerate(counts, start=1):
        files = []
        for _ in range(count):
            file_num += 1
            files.append(f"src/file_{file_num}.py")
        commits.append(CommitStep(order=idx, message=f"c{idx}", files=files))
    return DevelopmentPlan(project_summary="", detected_stack=[], commits=commits)


def test_enforce_commit_bounds_splits_to_min() -> None:
    plan = _plan_with_counts(6, 4)
    adjusted = enforce_commit_bounds(plan, min_commits=4, max_commits=10, file_count=10)
    assert len(adjusted.commits) >= 4
    assert len(adjusted.commits) <= 10


def test_enforce_commit_bounds_merges_to_max() -> None:
    plan = _plan_with_counts(1, 1, 1, 1, 1, 1)
    adjusted = enforce_commit_bounds(plan, min_commits=1, max_commits=3, file_count=6)
    assert len(adjusted.commits) <= 3


def test_enforce_commit_bounds_labels_splits_naturally() -> None:
    # Force repeated splits of one commit and verify labels stay human-like.
    plan = _plan_with_counts(12)
    adjusted = enforce_commit_bounds(plan, min_commits=6, max_commits=12, file_count=12)
    messages = [c.message for c in adjusted.commits]
    assert all("(part " not in m for m in messages)
    assert any("(follow-up)" in m for m in messages)
