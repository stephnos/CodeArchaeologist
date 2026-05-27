from __future__ import annotations

import fnmatch
from pathlib import Path

from retro_git.config import DEFAULT_IGNORE_DIRS, DEFAULT_IGNORE_FILES, DEFAULT_IGNORE_GLOBS
from retro_git.models import FileEntry


def _should_ignore(relative: Path, include_secrets: bool) -> bool:
    parts = relative.parts
    if any(part in DEFAULT_IGNORE_DIRS for part in parts):
        return True
    if relative.name in DEFAULT_IGNORE_FILES:
        return True
    if not include_secrets and (
        relative.name == ".env" or relative.name.startswith(".env.")
    ):
        return True
    rel_str = relative.as_posix()
    for pattern in DEFAULT_IGNORE_GLOBS:
        if fnmatch.fnmatch(relative.name, pattern) or fnmatch.fnmatch(rel_str, pattern):
            return True
    return False


def scan_codebase(
    root: Path,
    *,
    include_secrets: bool = False,
) -> list[FileEntry]:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"source is not a directory: {root}")

    entries: list[FileEntry] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if _should_ignore(relative, include_secrets):
            continue
        stat = path.stat()
        entries.append(
            FileEntry(
                path=relative.as_posix(),
                size_bytes=stat.st_size,
                extension=path.suffix.lower(),
            )
        )
    return entries


def detect_stack_hints(root: Path, files: list[FileEntry]) -> list[str]:
    paths = {f.path for f in files}
    hints: list[str] = []

    markers: list[tuple[str, str]] = [
        ("pyproject.toml", "python"),
        ("requirements.txt", "python"),
        ("Pipfile", "python"),
        ("package.json", "nodejs"),
        ("pnpm-lock.yaml", "pnpm"),
        ("yarn.lock", "yarn"),
        ("Cargo.toml", "rust"),
        ("go.mod", "go"),
        ("pom.xml", "java-maven"),
        ("build.gradle", "java-gradle"),
        ("Gemfile", "ruby"),
        ("composer.json", "php"),
        ("Dockerfile", "docker"),
        ("docker-compose.yml", "docker-compose"),
        ("docker-compose.yaml", "docker-compose"),
        (".github/workflows", "github-actions"),
    ]
    for marker, label in markers:
        if marker.endswith("/"):
            prefix = marker
            if any(p.startswith(prefix) for p in paths):
                hints.append(label)
        elif marker in paths:
            hints.append(label)

    if any("alembic" in p or "migrations" in p for p in paths):
        hints.append("database-migrations")
    if any(p.endswith((".tsx", ".jsx", ".vue")) for p in paths):
        hints.append("frontend")
    if any(p.endswith((".py",)) and ("api/" in p or "routes" in p) for p in paths):
        hints.append("api")

    seen: set[str] = set()
    ordered: list[str] = []
    for h in hints:
        if h not in seen:
            seen.add(h)
            ordered.append(h)
    return ordered
