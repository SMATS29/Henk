"""Centrale gateway voor alle modelcalls."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable

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
        self._on_token_usage: Callable[[int, int], None] | None = None

    @property
    def token_tracker(self) -> TokenTracker:
        return self._token_tracker

    @property
    def call_count(self) -> int:
        return self._call_count

    @property
    def on_token_usage(self) -> Callable[[int, int], None] | None:
        return self._on_token_usage

    @on_token_usage.setter
    def on_token_usage(self, callback: Callable[[int, int], None] | None) -> None:
        self._on_token_usage = callback

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
            if hasattr(self._router, "get_provider_candidates"):
                providers = self._router.get_provider_candidates(role, require_tools=require_tools)
            else:
                providers = [self._router.get_provider(role, require_tools=require_tools)]
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

        last_error: ProviderRequestError | None = None
        for index, provider in enumerate(providers, start=1):
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
                    "attempt": index,
                }
            )

            try:
                response = provider.chat(messages=messages, system=system, tools=tools, max_tokens=max_tokens)
            except ProviderRequestError as error:
                retrying_with_fallback = index < len(providers) and self._should_retry_with_fallback(error)
                self._log_event(
                    {
                        "type": "model.error",
                        "purpose": purpose,
                        "role": role.value,
                        "provider": provider_label,
                        "reason": error.reason,
                        "detail": error.detail,
                        "attempt": index,
                        "retrying_with_fallback": retrying_with_fallback,
                    }
                )
                last_error = error
                if retrying_with_fallback:
                    continue
                raise

            self._token_tracker.add(response.input_tokens, response.output_tokens)
            if self._on_token_usage:
                self._on_token_usage(response.input_tokens, response.output_tokens)
            self._log_event(
                {
                    "type": "model.response",
                    "purpose": purpose,
                    "role": role.value,
                    "provider": provider_label,
                    "input_tokens": response.input_tokens,
                    "output_tokens": response.output_tokens,
                    "tool_call_count": len(response.tool_calls or []),
                    "attempt": index,
                }
            )
            return ModelCallResult(provider=provider, response=response)

        if last_error is not None:
            raise last_error
        raise RuntimeError("Geen modelproviders beschikbaar na selectie.")

    def _should_retry_with_fallback(self, error: ProviderRequestError) -> bool:
        return error.reason in {"model_unavailable", "network_unavailable"}

    def _log_event(self, event: dict[str, Any]) -> None:
        if self._transcript is None:
            return
        payload = {"session_id": self._transcript.session_id, **event}
        self._transcript.log_event(payload)
