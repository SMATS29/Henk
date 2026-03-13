from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class ToolCall:
    """Een tool-aanroep van het model."""

    id: str
    name: str
    parameters: dict[str, Any]


@dataclass
class ProviderResponse:
    """Uniform antwoord van elke provider."""

    text: str | None
    tool_calls: list[ToolCall] | None
    raw: Any = None
    input_tokens: int = 0
    output_tokens: int = 0


class BaseProvider(ABC):
    """Interface voor alle model providers."""

    name: str

    @abstractmethod
    def chat(
        self,
        messages: list[dict[str, Any]],
        system: str,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 1024,
    ) -> ProviderResponse:
        """Stuur een chat-verzoek naar het model."""

    @abstractmethod
    def supports_tools(self) -> bool:
        """Geeft aan of deze provider tool-calling ondersteunt."""

    @abstractmethod
    def format_assistant_message(self, response: ProviderResponse) -> dict[str, Any]:
        """Formatteer assistant-antwoord zodat het terug in history kan."""

    def format_tool_result(self, tool_call_id: str, result: str) -> dict[str, Any]:
        return {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": tool_call_id, "content": result}],
        }
