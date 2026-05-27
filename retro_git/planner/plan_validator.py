from __future__ import annotations

from retro_git.models import CommitStep, DevelopmentPlan, Manifest


def expand_commit_files(files: list[str], manifest_paths: set[str]) -> set[str]:
    expanded: set[str] = set()
    for entry in files:
        entry = entry.strip().replace("\\", "/")
        if not entry:
            continue
        if entry in manifest_paths:
            expanded.add(entry)
            continue
        prefix = entry if entry.endswith("/") else f"{entry}/"
        matched = {p for p in manifest_paths if p.startswith(prefix)}
        if matched:
            expanded.update(matched)
            continue
        raise ValueError(f"plan references unknown path: {entry}")
    return expanded


def validate_plan(plan: DevelopmentPlan, manifest: Manifest) -> list[CommitStep]:
    manifest_paths = set(manifest.paths())
    if not manifest_paths:
        raise ValueError("manifest has no files to commit")

    assigned: dict[str, int] = {}
    normalized_steps: list[tuple[CommitStep, set[str]]] = []

    for step in sorted(plan.commits, key=lambda s: s.order):
        paths = expand_commit_files(step.files, manifest_paths)
        if not paths:
            raise ValueError(f"commit order {step.order} has no resolvable files")
        for path in paths:
            if path in assigned:
                raise ValueError(
                    f"path {path!r} assigned to commits {assigned[path]} and {step.order}"
                )
            assigned[path] = step.order
        normalized_steps.append((step, paths))

    missing = manifest_paths - set(assigned)
    extra = set(assigned) - manifest_paths
    if missing:
        raise ValueError(
            f"plan missing {len(missing)} file(s), e.g. {sorted(missing)[:5]}"
        )
    if extra:
        raise ValueError(f"plan includes paths not in manifest: {sorted(extra)[:5]}")

    return [step for step, _ in normalized_steps]
