from __future__ import annotations

from retro_git.models import CommitStep, DevelopmentPlan, Manifest
from retro_git.planner.plan_validator import expand_commit_files


def repair_plan(plan: DevelopmentPlan, manifest: Manifest) -> DevelopmentPlan:
    """
    Best-effort repair for imperfect LLM plans.

    - Drops unknown file references.
    - Expands directory entries into concrete files.
    - Removes duplicates across commits (first assignment wins).
    - Appends one final commit for any still-missing files.
    """
    manifest_paths = set(manifest.paths())
    if not manifest_paths:
        return plan

    assigned: set[str] = set()
    repaired_steps: list[CommitStep] = []

    for step in sorted(plan.commits, key=lambda s: s.order):
        resolved: list[str] = []
        seen_in_step: set[str] = set()
        for raw in step.files:
            try:
                expanded = expand_commit_files([raw], manifest_paths)
            except ValueError:
                # Ignore unknown references (e.g. hallucinated Dockerfile).
                continue
            for path in sorted(expanded):
                if path in seen_in_step or path in assigned:
                    continue
                seen_in_step.add(path)
                assigned.add(path)
                resolved.append(path)

        if not resolved:
            continue

        repaired_steps.append(
            CommitStep(
                order=len(repaired_steps) + 1,
                message=step.message,
                intent=step.intent,
                files=resolved,
            )
        )

    missing = sorted(manifest_paths - assigned)
    if missing:
        repaired_steps.append(
            CommitStep(
                order=len(repaired_steps) + 1,
                message="chore: add remaining files",
                intent="Auto-repaired missing files from LLM plan",
                files=missing,
            )
        )

    if not repaired_steps:
        repaired_steps.append(
            CommitStep(
                order=1,
                message="chore: initialize project files",
                intent="Fallback repaired plan",
                files=sorted(manifest_paths),
            )
        )

    return DevelopmentPlan(
        project_summary=(plan.project_summary or "").strip(),
        detected_stack=list(plan.detected_stack),
        commits=repaired_steps,
    )
