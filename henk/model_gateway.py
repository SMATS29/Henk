"""Centrale gateway voor alle modelcalls."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from henk.router import ModelRole, ModelRouter, ProviderSelectionError
from henk.router.providers.base import BaseProvider, ProviderRequestError, ProviderResponse
from henk.token_tracker import TokenTracker
from henk.transcript import TranscriptWriter


@dataclass
class ModelCallResult:
    provider: BaseProvider
    response: ProviderResponse


class ModelGateway:
    """Centraliseert providerselectie, modelcalls en debuglogging."""

    def __init__(self, router: ModelRouter, transcript: TranscriptWriter | None = None):
        self._router = router
        self._transcript = transcript
        self._token_tracker = TokenTracker()
        self._call_count = 0

    @property
    def token_tracker(self) -> TokenTracker:
        return self._token_tracker

    @property
    def call_count(self) -> int:
        return self._call_count

    def chat(
        self,
        *,
        role: ModelRole,
        messages: list[dict[str, Any]],
        system: str,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 1024,
        purpose: str,
        require_tools: bool = False,
    ) -> ModelCallResult:
        try:
            provider = self._router.get_provider(role, require_tools=require_tools)
        except ProviderSelectionError as error:
            self._log_event(
                {
                    "type": "model.error",
                    "purpose": purpose,
                    "role": role.value,
                    "reason": "selection_failed",
                    "attempts": [asdict(attempt) for attempt in error.attempts],
                }
            )
            raise

        provider_label = self._router.provider_label(provider)
        self._call_count += 1
        self._log_event(
            {
                "type": "model.request",
                "purpose": purpose,
                "role": role.value,
                "provider": provider_label,
                "message_count": len(messages),
                "has_tools": bool(tools),
                "max_tokens": max_tokens,
            }
        )

        try:
            response = provider.chat(messages=messages, system=system, tools=tools, max_tokens=max_tokens)
        except ProviderRequestError as error:
            self._log_event(
                {
                    "type": "model.error",
                    "purpose": purpose,
                    "role": role.value,
                    "provider": provider_label,
                    "reason": error.reason,
                    "detail": error.detail,
                }
            )
            raise

        self._token_tracker.add(response.input_tokens, response.output_tokens)
        self._log_event(
            {
                "type": "model.response",
                "purpose": purpose,
                "role": role.value,
                "provider": provider_label,
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                "tool_call_count": len(response.tool_calls or []),
            }
        )
        return ModelCallResult(provider=provider, response=response)

    def _log_event(self, event: dict[str, Any]) -> None:
        if self._transcript is None:
            return
        payload = {"session_id": self._transcript.session_id, **event}
        self._transcript.log_event(payload)
