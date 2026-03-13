from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class StepStatus(str, Enum):
    """Status van een skill-stap."""

    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class SkillStep:
    """Een enkele stap in een skill."""

    number: int
    title: str
    instruction: str
    action: str
    expected_output: str
    status: StepStatus = StepStatus.PENDING
    result: str | None = None
    error: str | None = None


@dataclass
class Skill:
    """Een geparsed skill-document."""

    name: str
    summary: str
    tags: list[str]
    tools_required: list[str]
    steps: list[SkillStep]
    source_path: str


@dataclass
class SkillRun:
    """Een actieve skill-uitvoering."""

    skill: Skill
    current_step: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None

    @property
    def is_complete(self) -> bool:
        return all(step.status in (StepStatus.COMPLETED, StepStatus.SKIPPED) for step in self.skill.steps)

    @property
    def active_step(self) -> SkillStep | None:
        if self.current_step < len(self.skill.steps):
            return self.skill.steps[self.current_step]
        return None

    def advance(self) -> SkillStep | None:
        self.current_step += 1
        return self.active_step
