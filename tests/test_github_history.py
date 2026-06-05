from retro_git.github_history import parse_github_repo_url
from retro_git.undo import UndoRecord, save_undo_record
from retro_git.github_history import last_published_github_url


def test_parse_github_repo_url() -> None:
    assert parse_github_repo_url("https://github.com/octocat/Hello-World") == (
        "octocat",
        "Hello-World",
    )
    assert parse_github_repo_url("github.com/foo/bar.git") == ("foo", "bar")
    assert parse_github_repo_url("https://github.com/foo/bar/tree/main") == (
        "foo",
        "bar",
    )


def test_last_published_github_url_from_record(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("retro_git.undo.UNDO_DIR", tmp_path)
    monkeypatch.setattr("retro_git.undo.UNDO_FILE", tmp_path / "last-run.json")
    save_undo_record(
        UndoRecord(
            project_path="/tmp/proj",
            backup_path=None,
            relocated=False,
            separate_target="/tmp/out",
            published_github=True,
            github_owner="stephnos",
            github_repo="my-app",
            github_url="https://github.com/stephnos/my-app",
        )
    )
    assert last_published_github_url() == "https://github.com/stephnos/my-app"
