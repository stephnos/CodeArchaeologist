import json
from pathlib import Path

from retro_git.undo import (
    UNDO_FILE,
    UndoRecord,
    can_undo,
    clear_undo_record,
    load_undo_record,
    save_undo_record,
)


def test_undo_record_roundtrip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("retro_git.undo.UNDO_DIR", tmp_path)
    monkeypatch.setattr("retro_git.undo.UNDO_FILE", tmp_path / "last-run.json")

    record = UndoRecord(
        project_path="/tmp/proj",
        backup_path="/tmp/proj.old",
        relocated=True,
        separate_target=None,
        published_github=False,
        github_owner=None,
        github_repo=None,
    )
    save_undo_record(record)
    loaded = load_undo_record()
    assert loaded is not None
    assert loaded.project_path == "/tmp/proj"
    clear_undo_record()
    assert load_undo_record() is None


def test_can_undo_relocate(tmp_path: Path, monkeypatch) -> None:
    proj = tmp_path / "app"
    backup = tmp_path / "app.old"
    proj.mkdir()
    backup.mkdir()
    record = UndoRecord(
        project_path=str(proj),
        backup_path=str(backup),
        relocated=True,
        separate_target=None,
        published_github=False,
        github_owner=None,
        github_repo=None,
    )
    ok, msg = can_undo(record)
    assert ok is True
    assert "Restore" in msg
