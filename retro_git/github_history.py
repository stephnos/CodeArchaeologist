from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass

from retro_git.github_publish import gh_authenticated
from retro_git.undo import load_undo_record

_GITHUB_URL = re.compile(
    r"(?:https?://)?(?:www\.)?github\.com/(?P<owner>[^/]+)/(?P<repo>[^/#?]+)",
    re.IGNORECASE,
)


class GitHubHistoryError(Exception):
    pass


@dataclass(frozen=True)
class CommitSummary:
    order: int
    sha: str
    message: str
    additions: int
    deletions: int


def parse_github_repo_url(url: str) -> tuple[str, str]:
    url = url.strip().removesuffix(".git")
    match = _GITHUB_URL.search(url)
    if not match:
        raise GitHubHistoryError(
            "Invalid GitHub URL. Use https://github.com/owner/repo"
        )
    owner = match.group("owner")
    repo = match.group("repo").removesuffix(".git")
    return owner, repo


def last_published_github_url() -> str | None:
    record = load_undo_record()
    if not record or not record.published_github:
        return None
    if record.github_url:
        return record.github_url
    if record.github_owner and record.github_repo:
        return f"https://github.com/{record.github_owner}/{record.github_repo}"
    return None


def _run_gh_graphql(owner: str, repo: str, *, limit: int = 100) -> dict:
    query = """
query($owner: String!, $name: String!, $first: Int!) {
  repository(owner: $owner, name: $name) {
    defaultBranchRef {
      target {
        ... on Commit {
          history(first: $first) {
            nodes {
              abbreviatedOid
              message
              additions
              deletions
            }
          }
        }
      }
    }
  }
}
"""
    payload = json.dumps(
        {"query": query, "variables": {"owner": owner, "name": repo, "first": limit}}
    )
    result = subprocess.run(
        ["gh", "api", "graphql", "--input", "-"],
        input=payload,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        raise GitHubHistoryError(err or "gh api graphql failed")
    return json.loads(result.stdout)


def fetch_commit_history(
    owner: str,
    repo: str,
    *,
    limit: int = 100,
) -> list[CommitSummary]:
    if not gh_authenticated():
        raise GitHubHistoryError("GitHub CLI is not logged in. Run: gh auth login")

    data = _run_gh_graphql(owner, repo, limit=limit)
    if data.get("errors"):
        msg = data["errors"][0].get("message", "GitHub API error")
        raise GitHubHistoryError(msg)

    repo_data = data.get("data", {}).get("repository")
    if not repo_data:
        raise GitHubHistoryError(f"Repository not found: {owner}/{repo}")

    ref = repo_data.get("defaultBranchRef")
    if not ref or not ref.get("target"):
        raise GitHubHistoryError(f"No commits on default branch for {owner}/{repo}")

    nodes = ref["target"]["history"]["nodes"]
    # GitHub returns newest-first; show chronological (oldest first).
    nodes = list(reversed(nodes))
    commits: list[CommitSummary] = []
    for idx, node in enumerate(nodes, start=1):
        message = (node.get("message") or "").strip().splitlines()[0]
        commits.append(
            CommitSummary(
                order=idx,
                sha=node.get("abbreviatedOid") or "",
                message=message,
                additions=int(node.get("additions") or 0),
                deletions=int(node.get("deletions") or 0),
            )
        )
    return commits
