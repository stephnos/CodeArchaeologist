from __future__ import annotations

from pathlib import Path


def read_text_lines(path: Path) -> list[str] | None:
    """
    Return source lines (newline characters preserved) for a text file.

    Returns None for binary files, which must be treated as atomic (copied
    verbatim) rather than split into line ranges.
    """
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in data:
        return None
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return text.splitlines(keepends=True)


def is_binary(path: Path) -> bool:
    return read_text_lines(path) is None
