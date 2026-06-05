from retro_git.old_repos import delete_old_backup, discover_old_backups, is_old_backup_name


def test_is_old_backup_name() -> None:
    assert is_old_backup_name("myapp.old")
    assert is_old_backup_name("myapp.old.2")
    assert not is_old_backup_name("myapp")
    assert not is_old_backup_name("old")


def test_discover_old_backups(tmp_path) -> None:
    root = tmp_path / "old"
    root.mkdir()
    (root / "keep").mkdir()
    (root / "proj.old").mkdir()
    (root / "other.old.2").mkdir()

    backups, resolved = discover_old_backups(root)
    names = [b["name"] for b in backups]
    assert resolved == str(root.resolve())
    assert names == ["other.old.2", "proj.old"]


def test_delete_old_backup(tmp_path) -> None:
    root = tmp_path / "old"
    root.mkdir()
    backup = root / "proj.old"
    backup.mkdir()
    (backup / "file.txt").write_text("x", encoding="utf-8")

    delete_old_backup(backup, root)
    assert not backup.exists()


def test_delete_rejects_outside_root(tmp_path) -> None:
    root = tmp_path / "old"
    root.mkdir()
    outside = tmp_path / "evil.old"
    outside.mkdir()

    try:
        delete_old_backup(outside, root)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "inside" in str(exc).lower()
