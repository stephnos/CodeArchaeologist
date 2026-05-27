from __future__ import annotations

from retro_git.models import CommitStep, DevelopmentPlan


def normalize_plan(plan: DevelopmentPlan) -> DevelopmentPlan:
    ordered = sorted(plan.commits, key=lambda s: s.order)
    renumbered: list[CommitStep] = []
    for idx, step in enumerate(ordered, start=1):
        renumbered.append(
            CommitStep(
                order=idx,
                message=step.message.strip(),
                intent=step.intent.strip(),
                files=list(step.files),
            )
        )
    return DevelopmentPlan(
        project_summary=plan.project_summary.strip(),
        detected_stack=list(plan.detected_stack),
        commits=renumbered,
    )
