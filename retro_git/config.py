from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

DEFAULT_IGNORE_DIRS = {
    ".git",
    ".retro-git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    ".next",
    ".nuxt",
    "coverage",
    "htmlcov",
    ".idea",
    ".vscode",
}

DEFAULT_IGNORE_FILES = {
    ".DS_Store",
    "Thumbs.db",
}

DEFAULT_IGNORE_GLOBS = (
    "*.pyc",
    "*.pyo",
    "*.egg-info",
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
    return Settings(
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        ollama_model=os.getenv("OLLAMA_MODEL", "llama3.2"),
        groq_api_key=os.getenv("GROQ_API_KEY"),
        groq_model=os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
        author_name=os.getenv("RETRO_GIT_AUTHOR_NAME", "Retro Git"),
        author_email=os.getenv("RETRO_GIT_AUTHOR_EMAIL", "retro-git@local"),
    )
