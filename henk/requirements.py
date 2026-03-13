from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class RequirementsStatus(str, Enum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    EXECUTING = "executing"
    EVALUATED = "evaluated"


@dataclass
class Requirements:
    task_description: str
    specifications: str = ""
    status: RequirementsStatus = RequirementsStatus.DRAFT
    skill_name: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    confirmed_at: datetime | None = None
    completed_at: datetime | None = None
    result: str | None = None

    def add_specification(self, spec: str) -> None:
        if self.status not in (RequirementsStatus.DRAFT, RequirementsStatus.CONFIRMED):
            return
        self.specifications += f"\n- {spec}" if self.specifications else f"- {spec}"

    def confirm(self) -> None:
        self.status = RequirementsStatus.CONFIRMED
        self.confirmed_at = datetime.now()

    def start_execution(self) -> None:
        self.status = RequirementsStatus.EXECUTING

    def complete(self, result: str) -> None:
        self.status = RequirementsStatus.EVALUATED
        self.completed_at = datetime.now()
        self.result = result

    def fail(self, reason: str) -> None:
        self.status = RequirementsStatus.EVALUATED
        self.completed_at = datetime.now()
        self.result = f"Mislukt: {reason}"
