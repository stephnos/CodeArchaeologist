from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Literal

import httpx
from pydantic import ValidationError

from retro_git.config import Settings, load_settings
from retro_git.llm.prompts import SYSTEM_PROMPT, build_user_prompt, extract_json_object
from retro_git.models import DevelopmentPlan, Manifest
from retro_git.scanner.manifest import manifest_for_llm, manifest_to_tree_text

ProviderName = Literal["ollama", "groq", "heuristic"]


class LLMProvider(ABC):
    @abstractmethod
    def generate_plan(
        self,
        manifest: Manifest,
        *,
        min_commits: int,
        max_commits: int,
    ) -> DevelopmentPlan:
        raise NotImplementedError


class OllamaProvider(LLMProvider):
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()

    def generate_plan(
        self,
        manifest: Manifest,
        *,
        min_commits: int,
        max_commits: int,
    ) -> DevelopmentPlan:
        suggested = _suggested_commit_count(len(manifest.files), min_commits, max_commits)
        user_prompt = build_user_prompt(
            stack_hints=manifest.stack_hints,
            manifest_json=manifest_for_llm(manifest),
            tree_text=manifest_to_tree_text(manifest),
            file_count=len(manifest.files),
            total_bytes=manifest.total_bytes,
            min_commits=min_commits,
            max_commits=max_commits,
            suggested_commit_count=suggested,
        )
        url = f"{self.settings.ollama_base_url.rstrip('/')}/api/chat"
        payload = {
            "model": self.settings.ollama_model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "format": "json",
        }
        with httpx.Client(timeout=600.0) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
        content = data.get("message", {}).get("content", "")
        return _parse_plan(content)

    def check_available(self) -> bool:
        try:
            url = f"{self.settings.ollama_base_url.rstrip('/')}/api/tags"
            with httpx.Client(timeout=5.0) as client:
                client.get(url).raise_for_status()
            return True
        except (httpx.HTTPError, OSError):
            return False


class GroqProvider(LLMProvider):
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()
        if not self.settings.groq_api_key:
            raise ValueError("GROQ_API_KEY is not set")

    def generate_plan(
        self,
        manifest: Manifest,
        *,
        min_commits: int,
        max_commits: int,
    ) -> DevelopmentPlan:
        try:
            from groq import Groq
        except ImportError as exc:
            raise ValueError(
                "Install groq support: pip install 'retro-git[groq]'"
            ) from exc

        suggested = _suggested_commit_count(len(manifest.files), min_commits, max_commits)
        user_prompt = build_user_prompt(
            stack_hints=manifest.stack_hints,
            manifest_json=manifest_for_llm(manifest),
            tree_text=manifest_to_tree_text(manifest),
            file_count=len(manifest.files),
            total_bytes=manifest.total_bytes,
            min_commits=min_commits,
            max_commits=max_commits,
            suggested_commit_count=suggested,
        )
        client = Groq(api_key=self.settings.groq_api_key)
        completion = client.chat.completions.create(
            model=self.settings.groq_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )
        content = completion.choices[0].message.content or ""
        return _parse_plan(content)


def get_provider(name: ProviderName, settings: Settings | None = None) -> LLMProvider:
    settings = settings or load_settings()
    if name == "ollama":
        return OllamaProvider(settings)
    if name == "groq":
        return GroqProvider(settings)
    if name == "heuristic":
        from retro_git.planner.heuristic_planner import HeuristicPlanner

        return HeuristicPlanner()
    raise ValueError(f"unknown provider: {name}")


def _suggested_commit_count(file_count: int, min_commits: int, max_commits: int) -> int:
    if file_count <= 5:
        raw = 3
    elif file_count <= 20:
        raw = 6
    elif file_count <= 80:
        raw = 12
    else:
        raw = 20
    return max(min_commits, min(max_commits, raw))


def _parse_plan(content: str) -> DevelopmentPlan:
    raw = extract_json_object(content)
    try:
        data = json.loads(raw)
        return DevelopmentPlan.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(f"invalid plan JSON from LLM: {exc}") from exc
