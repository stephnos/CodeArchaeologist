from pathlib import Path

from retro_git.layout import apply_relocate, resolve_layout


def test_blank_target_relocates(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "myapp"
    project.mkdir()
    (project / "main.py").write_text("print('hi')\n", encoding="utf-8")
    old_root = tmp_path / "old-workspaces"
    monkeypatch.setenv("RETRO_GIT_OLD_ROOT", str(old_root))

    layout, err = resolve_layout(str(project), "")
    assert err is None
    assert layout is not None
    assert layout.relocate_to_old is True
    assert layout.target == project.resolve()
    assert layout.backup_path == old_root / "myapp.old"


def test_explicit_target(tmp_path: Path) -> None:
    src = tmp_path / "src"
    out = tmp_path / "out"
    src.mkdir()
    out.mkdir()
    layout, err = resolve_layout(str(src), str(out))
    assert err is None
    assert layout is not None
    assert layout.relocate_to_old is False
    assert layout.target == out.resolve()


def test_apply_relocate_adds_number_if_backup_exists(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "myapp"
    project.mkdir()
    (project / "main.py").write_text("print('hi')\n", encoding="utf-8")
    old_root = tmp_path / ".old"
    monkeypatch.setenv("RETRO_GIT_OLD_ROOT", str(old_root))
    old_root.mkdir(parents=True, exist_ok=True)
    (old_root / "myapp.old").mkdir()

    layout, err = resolve_layout(str(project), "")
    assert err is None
    assert layout is not None

    moved_to = apply_relocate(layout)
    assert moved_to == old_root / "myapp.old.2"
    assert moved_to.is_dir()
    assert project.exists()
    assert project.is_dir()
    assert list(project.iterdir()) == []
