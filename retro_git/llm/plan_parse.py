from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from retro_git.models import DevelopmentPlan


def _looks_like_file_path(value: str) -> bool:
    value = value.strip()
    if not value or value.startswith(("http://", "https://")):
        return False
    return "/" in value or "." in value


def _extract_file_paths(value: Any) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()

    def walk(obj: Any) -> None:
        if isinstance(obj, str):
            if _looks_like_file_path(obj) and obj not in seen:
                seen.add(obj)
                found.append(obj)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)
        elif isinstance(obj, dict):
            for key, nested in obj.items():
                if isinstance(key, str) and _looks_like_file_path(key) and key not in seen:
                    seen.add(key)
                    found.append(key)
                walk(nested)

    walk(value)
    return found


def coerce_plan_dict(data: dict[str, Any]) -> dict[str, Any]:
    """
    Drop malformed commit entries and salvage file paths from broken LLM shapes.
    """
    commits_raw = data.get("commits", [])
    if not isinstance(commits_raw, list):
        commits_raw = []

    valid: list[dict[str, Any]] = []
    orphan_files: list[str] = []

    for item in commits_raw:
        if not isinstance(item, dict):
            continue
        if "order" in item and "message" in item:
            message = str(item["message"]).strip()
            if not message:
                orphan_files.extend(_extract_file_paths(item))
                continue
            files_raw = item.get("files", [])
            if isinstance(files_raw, list):
                files = [f for f in files_raw if isinstance(f, str)]
            else:
                files = _extract_file_paths(files_raw)
            valid.append(
                {
                    "order": int(item["order"]),
                    "message": message,
                    "intent": str(item.get("intent", "")),
                    "files": files,
                }
            )
        else:
            orphan_files.extend(_extract_file_paths(item))

    if orphan_files and valid:
        existing = set(valid[-1]["files"])
        for path in orphan_files:
            if path not in existing:
                valid[-1]["files"].append(path)
                existing.add(path)

    if not valid:
        raise ValueError("no valid commits in LLM plan")

    detected = data.get("detected_stack", [])
    if not isinstance(detected, list):
        detected = []

    return {
        "project_summary": str(data.get("project_summary", "")),
        "detected_stack": [str(x) for x in detected],
        "commits": valid,
    }


def parse_plan_json(content: str) -> DevelopmentPlan:
    from retro_git.llm.prompts import extract_json_object

    raw = extract_json_object(content)
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("LLM plan root must be a JSON object")
    coerced = coerce_plan_dict(data)
    try:
        return DevelopmentPlan.model_validate(coerced)
    except ValidationError as exc:
        raise ValueError(f"invalid plan JSON from LLM: {exc}") from exc
