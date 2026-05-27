from __future__ import annotations

import json

SYSTEM_PROMPT = """You are an expert software engineer reconstructing realistic Git history from a finished codebase.

Your task: produce a chronological development plan that a human team might have followed. The plan will be executed as sequential Git commits; each commit adds whole files (v1). The final union of all files MUST equal exactly the provided file manifest—no omissions, no extras.

Rules:
1. Order commits like real development: tooling/config → shared types/constants → data/models → core domain logic → integrations → API/routes → UI → tests → docs polish → CI/deploy.
2. Group files that belong together in one logical change (one feature/fix), typically 1–15 files per commit; avoid one giant commit or one file per commit unless justified (e.g. initial README).
3. Respect dependencies: do not commit importers before imported modules exist in the tree.
4. Use Conventional Commits: feat, fix, chore, docs, test, refactor, build, ci, style, perf. Scope optional (e.g. feat(api):).
5. Write concise commit messages (imperative mood, ≤72 chars subject).
6. Output ONLY valid JSON matching the schema—no markdown, no commentary.

Heuristics by path:
- Root config (package.json, pyproject.toml, Dockerfile, .github/) → early
- Migrations/schema → before repositories/services using them
- Shared utils/lib → before features
- Routes/controllers/handlers → after services/models
- Frontend pages/components → after API client/types if present
- Static assets and styling → after component skeletons
- Tests: either alongside feature commits (preferred for realism) or a dedicated pass before final polish—never before the code under test exists
- README/LICENSE: early stub ok; final doc updates near end

If manifest includes ambiguous files, infer from paths and extensions."""


def build_user_prompt(
    *,
    stack_hints: list[str],
    manifest_json: list[dict[str, object]],
    tree_text: str,
    file_count: int,
    total_bytes: int,
    min_commits: int,
    max_commits: int,
    suggested_commit_count: int,
) -> str:
    return f"""Reconstruct a realistic commit sequence for this project.

## Project signals
{json.dumps(stack_hints, indent=2)}

## File manifest ({file_count} files, {total_bytes} bytes)
{json.dumps(manifest_json, indent=2)}

## Directory tree (abbreviated)
{tree_text}

## Required JSON schema
{{
  "project_summary": "string",
  "detected_stack": ["string"],
  "commits": [
    {{
      "order": 1,
      "message": "chore: initialize project",
      "intent": "one sentence",
      "files": ["path/from/manifest", "other/path.py"]
    }}
  ]
}}

Constraints:
- Every manifest path must appear in exactly one commit's files list (use exact paths from manifest).
- commits ordered by ascending order (1-based, contiguous).
- Target {min_commits}–{max_commits} commits; aim for about {suggested_commit_count} commits for this project size.
- files entries are exact relative paths only (no directory globs)."""


def extract_json_object(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("LLM response did not contain a JSON object")
    return text[start : end + 1]
