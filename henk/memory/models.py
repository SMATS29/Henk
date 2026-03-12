"""Datamodellen voor Henk geheugen."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Provenance(str, Enum):
    """Herkomst van een geheugenwijziging."""

    USER_AUTHORED = "user-authored"
    AGENT_SUGGESTED = "agent-suggested"
    APPROVED_BY_USER = "approved-by-user"


class ChangeType(str, Enum):
    """Type geheugenwijziging."""

    CREATE = "create"
    UPDATE = "update"
    ARCHIVE = "archive"


@dataclass
class MemoryItem:
    """Een enkel geheugenonderdeel."""

    id: str
    path: str
    title: str
    description: str
    content: str
    score: int = 50
    last_used: datetime | None = None
    last_updated: datetime | None = None
    provenance: Provenance = Provenance.USER_AUTHORED
    tags: list[str] = field(default_factory=list)


@dataclass
class StagedChange:
    """Een voorgestelde geheugenwijziging in staging."""

    id: str
    change_type: ChangeType
    target_item_id: str | None
    proposed_content: str
    proposed_description: str
    provenance: Provenance
    reason: str
    timestamp: datetime
    suspicious: bool = False
    proposed_title: str = ""
    target_path: str | None = None
