from __future__ import annotations

import re
from pathlib import Path


def _top_level_starts(lines: list[str], path: str) -> list[int]:
    """Line indices where a new top-level unit begins (0 always included)."""
    ext = Path(path).suffix.lower()
    patterns: list[re.Pattern[str]] = []

    if ext == ".py":
        patterns = [
            re.compile(r"^(async\s+)?def\s+\w+"),
            re.compile(r"^class\s+\w+"),
        ]
    elif ext in {".js", ".jsx", ".ts", ".tsx"}:
        patterns = [
            re.compile(r"^export\s+(default\s+)?(async\s+)?function\s+\w+"),
            re.compile(r"^export\s+(default\s+)?class\s+\w+"),
            re.compile(r"^export\s+const\s+\w+"),
            re.compile(r"^(async\s+)?function\s+\w+"),
            re.compile(r"^class\s+\w+"),
        ]
    elif ext in {".go"}:
        patterns = [
            re.compile(r"^func\s+(\(.*\)\s+)?\w+"),
            re.compile(r"^type\s+\w+"),
        ]
    elif ext in {".rs"}:
        patterns = [
            re.compile(r"^pub\s+fn\s+\w+"),
            re.compile(r"^fn\s+\w+"),
            re.compile(r"^pub\s+struct\s+\w+"),
            re.compile(r"^struct\s+\w+"),
        ]

    starts = [0]
    for i, line in enumerate(lines):
        if i == 0:
            continue
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        if line[0] in " \t":
            continue
        if any(p.match(stripped) for p in patterns):
            starts.append(i)
    return sorted(set(starts))


def _blank_line_boundaries(lines: list[str]) -> list[int]:
    out: list[int] = []
    for i in range(1, len(lines)):
        if lines[i - 1].strip() == "":
            out.append(i)
    return out


def semantic_split_ranges(
    lines: list[str],
    path: str,
    k: int,
) -> list[tuple[int, int]]:
    """
    Partition file into k contiguous fragments, preferring cuts at
    function/class/export boundaries.
    """
    n = len(lines)
    if n == 0:
        return [(0, 0)]
    if k <= 1:
        return [(0, n)]

    units = _top_level_starts(lines, path)
    k = min(k, max(len(units), 1))

    if len(units) >= 2:
        # Merge top-level units into k groups.
        if k >= len(units):
            return [(units[i], units[i + 1] if i + 1 < len(units) else n) for i in range(len(units))]

        groups: list[list[int]] = [[] for _ in range(k)]
        for idx, start in enumerate(units):
            bucket = min(idx * k // len(units), k - 1)
            groups[bucket].append(start)

        ranges: list[tuple[int, int]] = []
        for gi, group in enumerate(groups):
            if not group:
                continue
            start = group[0]
            if gi + 1 < k:
                next_starts = [g[0] for g in groups[gi + 1 :] if g]
                end = next_starts[0] if next_starts else n
            else:
                end = n
            if start < end:
                ranges.append((start, end))
        if ranges and ranges[-1][1] < n:
            ranges[-1] = (ranges[-1][0], n)
        if ranges:
            return ranges

    # Fallback: size-based cuts on blank lines.
    boundaries = _blank_line_boundaries(lines) or list(range(1, n))
    cuts: list[int] = []
    for j in range(1, k):
        target = round(j * n / k)
        cut = min(boundaries, key=lambda v: (abs(v - target), v))
        cut = min(max(cut, 1), n - 1)
        cuts.append(cut)
    ordered = sorted(set(cuts))
    ranges = []
    prev = 0
    for cut in ordered:
        if cut <= prev:
            continue
        ranges.append((prev, cut))
        prev = cut
    ranges.append((prev, n))
    return ranges


def symbols_in_ranges(lines: list[str], ranges: list[tuple[int, int]], path: str) -> list[str]:
    """Names of defs/classes/exports introduced in the given line ranges."""
    ext = Path(path).suffix.lower()
    names: list[str] = []
    seen: set[str] = set()
    for start, end in ranges:
        for line in lines[start:end]:
            stripped = line.strip()
            for pattern in _symbol_patterns(ext):
                m = pattern.match(stripped)
                if m and m.group(1) not in seen:
                    seen.add(m.group(1))
                    names.append(m.group(1))
    return names[:4]


def _symbol_patterns(ext: str) -> list[re.Pattern[str]]:
    if ext == ".py":
        return [
            re.compile(r"^(?:async\s+)?def\s+(\w+)"),
            re.compile(r"^class\s+(\w+)"),
        ]
    if ext in {".js", ".jsx", ".ts", ".tsx"}:
        return [
            re.compile(r"^export\s+(?:default\s+)?(?:async\s+)?function\s+(\w+)"),
            re.compile(r"^export\s+(?:default\s+)?class\s+(\w+)"),
            re.compile(r"^export\s+const\s+(\w+)"),
            re.compile(r"^(?:async\s+)?function\s+(\w+)"),
            re.compile(r"^class\s+(\w+)"),
        ]
    if ext == ".rs":
        return [
            re.compile(r"^pub\s+fn\s+(\w+)"),
            re.compile(r"^fn\s+(\w+)"),
            re.compile(r"^pub\s+struct\s+(\w+)"),
            re.compile(r"^struct\s+(\w+)"),
            re.compile(r"^pub\s+enum\s+(\w+)"),
            re.compile(r"^enum\s+(\w+)"),
        ]
    if ext == ".go":
        return [
            re.compile(r"^func\s+(\w+)"),
            re.compile(r"^type\s+(\w+)"),
        ]
    return []


def scope_from_path(path: str) -> str:
    """Conventional-commit scope from a file path."""
    parts = Path(path).parts
    if len(parts) >= 2:
        return parts[-2]
    return Path(path).stem
