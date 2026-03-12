"""Basisinterfaces voor tools."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ErrorType(str, Enum):
    """Type toolfout voor retry-limieten."""

    CONTENT = "content"
    TECHNICAL = "technical"


@dataclass
class ToolError:
    """Beschrijving van een toolfout."""

    error_type: ErrorType
    message: str
    retry_useful: bool


@dataclass
class ToolResult:
    """Resultaat van een tool-uitvoering."""

    success: bool
    data: str | dict[str, Any] | None
    source_tag: str
    error: ToolError | None = None


class BaseTool:
    """Basis voor alle Henk tools."""

    name: str = "base"
    description: str = ""
    permissions: list[str] = []
    parameters: dict[str, Any] = {"type": "object", "properties": {}}

    def execute(self, **kwargs: Any) -> ToolResult:
        """Voer de tool uit."""
        raise NotImplementedError

    def classify_error(self, error: Exception) -> ErrorType:
        """Classificeer toolfouten."""
        return ErrorType.TECHNICAL
