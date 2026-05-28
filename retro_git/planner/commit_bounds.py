from __future__ import annotations

from retro_git.models import CommitStep, DevelopmentPlan


def enforce_commit_bounds(
    plan: DevelopmentPlan,
    *,
    min_commits: int,
    max_commits: int,
    file_count: int,
) -> DevelopmentPlan:
    """
    Enforce commit count range by splitting/merging commit file lists.

    - Splits largest commits until reaching min_commits.
    - Merges smallest adjacent commits until <= max_commits.
    - Never creates more commits than files.
    """
    if not plan.commits:
        return plan

    effective_min = min(min_commits, file_count)
    effective_max = min(max_commits, file_count)
    if effective_max < effective_min:
        effective_max = effective_min

    steps = [CommitStep.model_validate(s.model_dump()) for s in plan.commits]

    def largest_splittable_index() -> int | None:
        candidates = [(idx, len(step.files)) for idx, step in enumerate(steps) if len(step.files) > 1]
        if not candidates:
            return None
        return max(candidates, key=lambda t: t[1])[0]

    while len(steps) < effective_min:
        idx = largest_splittable_index()
        if idx is None:
            break
        step = steps[idx]
        half = len(step.files) // 2
        left_files = step.files[:half]
        right_files = step.files[half:]
        if not left_files or not right_files:
            break
        left = CommitStep(
            order=step.order,
            message=f"{step.message} (part 1)",
            intent=step.intent,
            files=left_files,
        )
        right = CommitStep(
            order=step.order + 1,
            message=f"{step.message} (part 2)",
            intent=step.intent,
            files=right_files,
        )
        steps[idx : idx + 1] = [left, right]

    while len(steps) > effective_max and len(steps) > 1:
        pair_idx = min(
            range(len(steps) - 1),
            key=lambda i: len(steps[i].files) + len(steps[i + 1].files),
        )
        a = steps[pair_idx]
        b = steps[pair_idx + 1]
        merged = CommitStep(
            order=a.order,
            message=a.message,
            intent=(a.intent or b.intent).strip(),
            files=[*a.files, *b.files],
        )
        steps[pair_idx : pair_idx + 2] = [merged]

    renumbered: list[CommitStep] = []
    for idx, step in enumerate(steps, start=1):
        renumbered.append(
            CommitStep(
                order=idx,
                message=step.message,
                intent=step.intent,
                files=list(step.files),
            )
        )

    return DevelopmentPlan(
        project_summary=plan.project_summary,
        detected_stack=list(plan.detected_stack),
        commits=renumbered,
    )
