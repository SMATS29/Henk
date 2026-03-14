from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


class ProviderRequestError(RuntimeError):
    """Gestructureerde fout tijdens een provider-request."""

    def __init__(self, provider_name: str, reason: str, detail: str = ""):
        self.provider_name = provider_name
        self.reason = reason
        self.detail = detail
        super().__init__(detail or f"Provider request mislukt: {provider_name} ({reason})")


def classify_provider_error(error: Exception) -> str:
    """Classificeer providerfouten voor duidelijke CLI-meldingen."""
    message = str(error).lower()
    if any(token in message for token in ("connection", "connect", "timeout", "timed out", "dns", "unreachable", "refused")):
        return "network_unavailable"
    if any(token in message for token in ("authentication", "auth", "api key", "unauthorized", "forbidden", "401", "403")):
        return "authentication_failed"
    return "request_failed"


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
