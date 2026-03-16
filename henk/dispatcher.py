"""Dispatcher: berichten tussen Conversation Thread en Work Thread."""

from __future__ import annotations

from dataclasses import dataclass

from henk.requirements import Requirements


@dataclass
class TaskMessage:
    run_id: str
    requirements: Requirements


@dataclass
class CancelMessage:
    run_id: str


@dataclass
class ProgressMessage:
    run_id: str
    status: str


@dataclass
class ResultMessage:
    run_id: str
    response: str
    success: bool
    error: str | None = None
