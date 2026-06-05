from __future__ import annotations

from pathlib import Path

from retro_git.models import BuildPlan, FileEdit, Manifest
from retro_git.textfiles import read_text_lines


def _simulate_present(edits: list[FileEdit]) -> dict[str, set[int]]:
    present: dict[str, set[int]] = {}
    for edit in edits:
        if edit.whole:
            continue
        if edit.mode == "reset":
            indices: set[int] = set()
            for rng in edit.ranges:
                indices.update(rng.indices())
            present[edit.path] = indices
        else:
            bucket = present.setdefault(edit.path, set())
            for rng in edit.ranges:
                bucket.update(rng.indices())
    return present


def validate_build_plan(plan: BuildPlan, manifest: Manifest, source: Path) -> None:
    """
    Ensure a v2 BuildPlan reconstructs the source exactly.

    Simulates append/reset steps to verify the final tree matches the source.
    """
    source = source.resolve()
    manifest_paths = set(manifest.paths())
    if not manifest_paths:
        raise ValueError("manifest has no files to commit")

    orders = [step.order for step in plan.steps]
    if orders != list(range(1, len(plan.steps) + 1)):
        raise ValueError(f"build plan orders not contiguous: {orders}")

    ordered_edits: list[FileEdit] = []
    whole_files: set[str] = set()

    for step in plan.steps:
        for edit in step.edits:
            if edit.path not in manifest_paths:
                raise ValueError(f"build plan references unknown path: {edit.path}")
            if edit.whole:
                if edit.path in whole_files:
                    raise ValueError(f"path {edit.path!r} introduced more than once")
                whole_files.add(edit.path)
                continue
            ordered_edits.append(edit)

    seen = {e.path for e in ordered_edits} | whole_files
    missing = manifest_paths - seen
    if missing:
        raise ValueError(
            f"build plan missing {len(missing)} file(s), e.g. {sorted(missing)[:5]}"
        )

    final_present = _simulate_present(ordered_edits)
    for path in whole_files:
        if not (source / path).is_file():
            raise ValueError(f"whole-file path missing on disk: {path}")

    for path, indices in final_present.items():
        lines = read_text_lines(source / path)
        if lines is None:
            raise ValueError(f"binary file {path!r} scheduled as line ranges")
        n = len(lines)
        if indices != set(range(n)):
            raise ValueError(
                f"final state for {path!r} has {len(indices)} lines, expected {n}"
            )
