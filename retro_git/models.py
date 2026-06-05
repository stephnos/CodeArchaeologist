from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


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


class LineRange(BaseModel):
    """Half-open range of 0-based source line indices: [start, end)."""

    start: int
    end: int

    @model_validator(mode="after")
    def check_bounds(self) -> "LineRange":
        if self.start < 0 or self.end < self.start:
            raise ValueError(f"invalid line range [{self.start}, {self.end})")
        return self

    @property
    def length(self) -> int:
        return self.end - self.start

    def indices(self) -> range:
        return range(self.start, self.end)


class FileEdit(BaseModel):
    """Lines of a source file that become present at a given commit."""

    path: str
    ranges: list[LineRange] = Field(default_factory=list)
    whole: bool = False  # binary/atomic files copied verbatim, ignoring ranges
    mode: Literal["append", "reset"] = "append"  # reset replaces file content with ranges


class BuildStep(BaseModel):
    """A v2 commit: incremental edits to one or more files."""

    order: int
    message: str
    intent: str = ""
    edits: list[FileEdit]

    @field_validator("message")
    @classmethod
    def message_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("commit message must not be empty")
        return v

    @field_validator("edits")
    @classmethod
    def edits_not_empty(cls, v: list[FileEdit]) -> list[FileEdit]:
        if not v:
            raise ValueError("build step must contain at least one edit")
        return v


class BuildPlan(BaseModel):
    """v2 plan: files built up incrementally so commits show realistic diffs."""

    project_summary: str = ""
    detected_stack: list[str] = Field(default_factory=list)
    steps: list[BuildStep]

    @field_validator("steps")
    @classmethod
    def steps_not_empty(cls, v: list[BuildStep]) -> list[BuildStep]:
        if not v:
            raise ValueError("build plan must contain at least one step")
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
