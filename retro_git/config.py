from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _git_config(key: str) -> str | None:
    result = subprocess.run(
        ["git", "config", "--global", key],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    value = (result.stdout or "").strip()
    return value or None


def default_author_identity() -> tuple[str, str]:
    """Env vars, then git global user.name/email, then built-in fallback."""
    name = os.getenv("RETRO_GIT_AUTHOR_NAME")
    email = os.getenv("RETRO_GIT_AUTHOR_EMAIL")
    if name and email:
        return name, email
    git_name = _git_config("user.name")
    git_email = _git_config("user.email")
    if git_name and git_email:
        return git_name, git_email
    return "Retro Git", "retro-git@local"

DEFAULT_IGNORE_DIRS = {
    ".git",
    ".retro-git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".nox",
    ".eggs",
    ".hypothesis",
    ".cache",
    ".parcel-cache",
    ".turbo",
    ".nyc_output",
    ".dart_tool",
    ".gradle",
    ".mvn",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    "out",
    "target",
    "vendor",
    "Pods",
    "DerivedData",
    "bin",
    "obj",
    ".next",
    ".nuxt",
    ".svelte-kit",
    "coverage",
    "htmlcov",
    "site-packages",
    "playwright-report",
    "test-results",
    ".idea",
    ".vscode",
}

DEFAULT_IGNORE_FILES = {
    ".DS_Store",
    "Thumbs.db",
    ".coverage",
    "coverage.xml",
    ".eslintcache",
    "npm-debug.log",
    "yarn-error.log",
}

DEFAULT_IGNORE_GLOBS = (
    "*.pyc",
    "*.pyo",
    "*.egg-info",
    "*.log",
    "*.lcov",
    ".env",
    ".env.*",
)


@dataclass(frozen=True)
class Settings:
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    groq_api_key: str | None = None
    groq_model: str = "llama-3.1-8b-instant"
    author_name: str = "Retro Git"
    author_email: str = "retro-git@local"


def load_settings() -> Settings:
    author_name, author_email = default_author_identity()
    return Settings(
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        ollama_model=os.getenv("OLLAMA_MODEL", "llama3.2"),
        groq_api_key=os.getenv("GROQ_API_KEY"),
        groq_model=os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
        author_name=author_name,
        author_email=author_email,
    )
