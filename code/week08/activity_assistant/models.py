"""M3 的四个角色契约。

每个角色都有明确的输入输出模型——这是"多智能体系统"与"四个 chatbot"的分界线。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Requirement(BaseModel):
    title: str = Field(min_length=2, max_length=20)
    goal: str
    target_users: str
    mechanics: list[str] = Field(min_length=1)
    rewards: list[str] = Field(min_length=1)
    constraints: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not self.missing


class AssetPlan(BaseModel):
    images: list[dict] = Field(default_factory=list)
    copywriting: dict[str, str] = Field(default_factory=dict)
    configs: dict[str, str] = Field(default_factory=dict)
    data_needs: list[str] = Field(default_factory=list)


class CodeArtifact(BaseModel):
    files: list[dict] = Field(default_factory=list)
    entry: str = "index.html"
    notes: str = ""


class ReviewIssue(BaseModel):
    severity: Literal["error", "warn", "info"]
    rule: str
    message: str


class ReviewReport(BaseModel):
    scores: dict[str, int] = Field(default_factory=dict)
    issues: list[ReviewIssue] = Field(default_factory=list)
    verdict: Literal["pass", "revise"] = "pass"

    @property
    def has_error(self) -> bool:
        return any(i.severity == "error" for i in self.issues)
