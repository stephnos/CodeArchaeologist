"""
v2 evolution planner.

Transforms a whole-file v1 DevelopmentPlan into a BuildPlan where files grow
incrementally using real source lines split at function/class boundaries.
"""

from __future__ import annotations

from pathlib import Path

from retro_git.models import (
    BuildPlan,
    BuildStep,
    DevelopmentPlan,
    FileEdit,
    LineRange,
    Manifest,
)
from retro_git.planner.plan_validator import expand_commit_files
from retro_git.planner.semantic_split import (
    scope_from_path,
    semantic_split_ranges,
    symbols_in_ranges,
)
from retro_git.textfiles import read_text_lines

DEFAULT_MIN_LINES_TO_SPLIT = 24
DEFAULT_MAX_FRAGMENTS = 6
_LINES_PER_FRAGMENT = 35


def _fragment_count(
    lines: list[str],
    path: str,
    *,
    max_fragments: int,
    min_lines_to_split: int,
) -> int:
    n = len(lines)
    if n < min_lines_to_split:
        return 1
    from retro_git.planner.semantic_split import _top_level_starts

    units = len(_top_level_starts(lines, path))
    if units >= 3:
        by_units = max(2, min(max_fragments, units // 2))
        by_size = max(1, min(max_fragments, n // _LINES_PER_FRAGMENT + 1))
        return max(2, min(max_fragments, max(by_units, by_size)))
    return max(1, min(max_fragments, n // _LINES_PER_FRAGMENT + 1))


def _pick_later_commits(intro_index: int, total: int, count: int) -> list[int | str]:
    available = list(range(intro_index + 1, total))
    if not available:
        return [f"extra:{j}" for j in range(count)]
    picks: list[int | str] = []
    for j in range(count):
        pos = int(round((j + 1) * len(available) / (count + 1))) - 1
        pos = min(max(pos, 0), len(available) - 1)
        picks.append(available[pos])
    return picks


def message_for_rework(path: str) -> str:
    scope = scope_from_path(path)
    name = Path(path).name
    return f"refactor({scope}): rework {name}"


def message_for_extension(path: str, lines: list[str], new_ranges: list[tuple[int, int]]) -> str:
    """Short conventional-commit message for a real code addition."""
    scope = scope_from_path(path)
    symbols = symbols_in_ranges(lines, new_ranges, path)
    if len(symbols) == 1:
        return f"feat({scope}): add {symbols[0]}"
    if len(symbols) > 1:
        return f"feat({scope}): add {', '.join(symbols[:3])}"
    name = Path(path).name
    new_lines = sum(end - start for start, end in new_ranges)
    if new_lines <= 8:
        return f"feat({scope}): add {name}"
    return f"feat({scope}): add more to {name}"


def build_evolution_plan(
    plan: DevelopmentPlan,
    manifest: Manifest,
    source: Path,
    *,
    max_fragments: int = DEFAULT_MAX_FRAGMENTS,
    min_lines_to_split: int = DEFAULT_MIN_LINES_TO_SPLIT,
) -> BuildPlan:
    source = source.resolve()
    ordered = sorted(plan.commits, key=lambda s: s.order)
    total = len(ordered)
    manifest_paths = set(manifest.paths())
    line_cache: dict[str, list[str] | None] = {}

    edits_by_commit: list[dict[str, list[tuple[int, int]]]] = [dict() for _ in ordered]
    extra_steps: list[tuple[str, tuple[int, int], str]] = []
    intro_at: dict[str, int] = {}
    file_fragments: dict[str, list[tuple[int, int]]] = {}
    whole_paths: set[str] = set()
    scheduled: set[str] = set()

    for ci, step in enumerate(ordered):
        paths = sorted(expand_commit_files(step.files, manifest_paths))
        for rel in paths:
            if rel in scheduled:
                continue
            scheduled.add(rel)
            if rel not in line_cache:
                line_cache[rel] = read_text_lines(source / rel)
            lines = line_cache[rel]
            if lines is None:
                edits_by_commit[ci].setdefault(rel, [])
                whole_paths.add(rel)
                intro_at[rel] = ci
                continue

            k = _fragment_count(
                lines,
                rel,
                max_fragments=max_fragments,
                min_lines_to_split=min_lines_to_split,
            )
            fragments = semantic_split_ranges(lines, rel, k)
            file_fragments[rel] = fragments
            intro_at[rel] = ci
            edits_by_commit[ci].setdefault(rel, []).append(fragments[0])

            if len(fragments) > 1:
                targets = _pick_later_commits(ci, total, len(fragments) - 1)
                for frag, tgt in zip(fragments[1:], targets):
                    if isinstance(tgt, str) and tgt.startswith("extra:"):
                        extra_steps.append((rel, frag, step.message))
                    else:
                        edits_by_commit[int(tgt)].setdefault(rel, []).append(frag)

    steps: list[BuildStep] = []
    shrink_done: set[str] = set()
    follow_batch: dict[str, int] = {}
    applied_fragments: dict[str, list[tuple[int, int]]] = {}
    dropped_fragments: dict[str, list[tuple[int, int]]] = {}

    for ci, step in enumerate(ordered):
        commit_edits = edits_by_commit[ci]
        if not commit_edits:
            continue
        intro_paths = {p for p, idx in intro_at.items() if idx == ci}

        primary_edits: list[FileEdit] = []
        follow_up_edits: list[FileEdit] = []

        for path in sorted(commit_edits):
            if path in whole_paths and not commit_edits[path]:
                primary_edits.append(FileEdit(path=path, ranges=[], whole=True))
                continue
            ordered_ranges = sorted(commit_edits[path])
            edit = FileEdit(
                path=path,
                ranges=[LineRange(start=s, end=e) for s, e in ordered_ranges],
            )
            if path in intro_paths:
                primary_edits.append(edit)
                applied_fragments[path] = list(ordered_ranges)
            else:
                follow_up_edits.append(edit)

        if primary_edits:
            steps.append(
                BuildStep(
                    order=len(steps) + 1,
                    message=step.message,
                    intent=step.intent,
                    edits=primary_edits,
                )
            )

        for edit in follow_up_edits:
            path = edit.path
            follow_batch[path] = follow_batch.get(path, 0) + 1
            frags = file_fragments.get(path, [])
            ordered_ranges = sorted((r.start, r.end) for r in edit.ranges)
            applied = applied_fragments.get(path, [])

            if (
                follow_batch[path] == 2
                and len(frags) >= 3
                and path not in shrink_done
                and len(applied) > 1
            ):
                shrink_done.add(path)
                to_drop = applied[1]
                child = sorted(set(applied) - {to_drop} | set(ordered_ranges))
                if set(child) != set(applied):
                    dropped_fragments.setdefault(path, []).append(to_drop)
                    applied_fragments[path] = child
                    steps.append(
                        BuildStep(
                            order=len(steps) + 1,
                            message=message_for_rework(path),
                            intent="Rework file with mixed line changes",
                            edits=[
                                FileEdit(
                                    path=path,
                                    ranges=[
                                        LineRange(start=s, end=e) for s, e in child
                                    ],
                                    mode="reset",
                                )
                            ],
                        )
                    )
                    continue

            if dropped_fragments.get(path):
                ordered_ranges = sorted(
                    {dropped_fragments[path].pop(0), *ordered_ranges}
                )

            for r in ordered_ranges:
                if r not in applied_fragments.setdefault(path, []):
                    applied_fragments[path].append(r)

            lines = line_cache.get(path)
            new_ranges = list(ordered_ranges)
            msg = (
                message_for_extension(path, lines, new_ranges)
                if lines
                else f"feat: add {Path(path).name}"
            )
            steps.append(
                BuildStep(
                    order=len(steps) + 1,
                    message=msg,
                    intent="Incremental file growth",
                    edits=[
                        FileEdit(
                            path=path,
                            ranges=[LineRange(start=s, end=e) for s, e in ordered_ranges],
                        )
                    ],
                )
            )

        chained = [
            (path, frag, base)
            for path, frag, base in extra_steps
            if intro_at.get(path) == ci
        ]
        for path, frag, _base in chained:
            lines = line_cache.get(path)
            msg = (
                message_for_extension(path, lines, [frag])
                if lines
                else f"feat: add {Path(path).name}"
            )
            if frag not in applied_fragments.setdefault(path, []):
                applied_fragments[path].append(frag)
            steps.append(
                BuildStep(
                    order=len(steps) + 1,
                    message=msg,
                    intent="Incremental file growth",
                    edits=[FileEdit(path=path, ranges=[LineRange(start=frag[0], end=frag[1])])],
                )
            )

    for path in sorted(dropped_fragments):
        for drop in dropped_fragments[path]:
            if drop not in applied_fragments.setdefault(path, []):
                applied_fragments[path].append(drop)
            lines = line_cache.get(path)
            msg = (
                message_for_extension(path, lines, [drop])
                if lines
                else f"feat: add {Path(path).name}"
            )
            steps.append(
                BuildStep(
                    order=len(steps) + 1,
                    message=msg,
                    intent="Restore trimmed fragment",
                    edits=[
                        FileEdit(
                            path=path,
                            ranges=[LineRange(start=drop[0], end=drop[1])],
                        )
                    ],
                )
            )

    return BuildPlan(
        project_summary=plan.project_summary,
        detected_stack=list(plan.detected_stack),
        steps=steps,
    )
