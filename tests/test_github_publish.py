from unittest.mock import MagicMock, patch

from retro_git.github_publish import github_repo_exact_name


def test_exact_name_rejects_redirect_alias() -> None:
    result = MagicMock(returncode=0, stdout="fraud-detector-ml.old\n")
    with patch("retro_git.github_publish.subprocess.run", return_value=result):
        assert github_repo_exact_name("stephnos", "fraud-detector-ml") is False


def test_exact_name_accepts_match() -> None:
    result = MagicMock(returncode=0, stdout="fraud-detector-ml\n")
    with patch("retro_git.github_publish.subprocess.run", return_value=result):
        assert github_repo_exact_name("stephnos", "fraud-detector-ml") is True
