import subprocess
from pathlib import Path

from retro_git.scanner.file_collection import collect_project_paths, is_git_repository


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def test_git_repo_uses_tracked_files_only(tmp_path: Path) -> None:
    repo = tmp_path / "proj"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "Test")

    (repo / "main.py").write_text("print('ok')\n", encoding="utf-8")
    (repo / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
    _git(repo, "add", "main.py", ".gitignore")
    _git(repo, "commit", "-m", "init")

    cache_dir = repo / "__pycache__"
    cache_dir.mkdir()
    (cache_dir / "main.cpython-312.pyc").write_bytes(b"junk")
    (repo / "scratch.txt").write_text("untracked\n", encoding="utf-8")

    assert is_git_repository(repo)
    paths = collect_project_paths(repo)
    assert paths == [".gitignore", "main.py"]


def test_include_untracked_respects_gitignore(tmp_path: Path) -> None:
    repo = tmp_path / "proj"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "Test")

    (repo / "main.py").write_text("x\n", encoding="utf-8")
    (repo / ".gitignore").write_text("scratch.txt\n", encoding="utf-8")
    _git(repo, "add", "main.py", ".gitignore")
    _git(repo, "commit", "-m", "init")
    (repo / "notes.txt").write_text("new\n", encoding="utf-8")
    (repo / "scratch.txt").write_text("ignored\n", encoding="utf-8")

    paths = collect_project_paths(repo, include_untracked=True)
    assert "main.py" in paths
    assert "notes.txt" in paths
    assert "scratch.txt" not in paths
