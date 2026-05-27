from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class CommitStep(BaseModel):
    order: int
    message: str
    intent: str = ""
    files: list[str] = Field(default_factory=list)

    @field_validator("message")
    @classmethod
    def message_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("commit message must not be empty")
        return v


class DevelopmentPlan(BaseModel):
    project_summary: str = ""
    detected_stack: list[str] = Field(default_factory=list)
    commits: list[CommitStep]

    @field_validator("commits")
    @classmethod
    def commits_not_empty(cls, v: list[CommitStep]) -> list[CommitStep]:
        if not v:
            raise ValueError("plan must contain at least one commit")
        return v


class FileEntry(BaseModel):
    path: str
    size_bytes: int
    extension: str = ""


class Manifest(BaseModel):
    root: str
    files: list[FileEntry] = Field(default_factory=list)
    stack_hints: list[str] = Field(default_factory=list)
    total_bytes: int = 0

    def paths(self) -> list[str]:
        return [f.path for f in self.files]
