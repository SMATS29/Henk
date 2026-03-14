from __future__ import annotations

from typing import Any

import anthropic

from henk.router.providers.base import (
    BaseProvider,
    ProviderRequestError,
    ProviderResponse,
    ToolCall,
    classify_provider_error,
)


class AnthropicProvider(BaseProvider):
    name = "anthropic"

    def __init__(self, api_key: str, model: str):
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def chat(
        self,
        messages: list[dict[str, Any]],
        system: str,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 1024,
    ) -> ProviderResponse:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools

        try:
            response = self._client.messages.create(**kwargs)
        except Exception as error:
            raise ProviderRequestError(self.name, classify_provider_error(error), str(error)) from error

        tool_calls: list[ToolCall] = []
        text_parts: list[str] = []
        for block in response.content:
            if getattr(block, "type", "") == "tool_use":
                tool_calls.append(ToolCall(id=block.id, name=block.name, parameters=dict(block.input)))
            elif hasattr(block, "text"):
                text_parts.append(block.text)

        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "input_tokens", 0) if usage else 0
        output_tokens = getattr(usage, "output_tokens", 0) if usage else 0

        if tool_calls:
            return ProviderResponse(
                text=None,
                tool_calls=tool_calls,
                raw=response,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
        return ProviderResponse(
            text="".join(text_parts).strip(),
            tool_calls=None,
            raw=response,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    def supports_tools(self) -> bool:
        return True

    def format_tool_result(self, tool_call_id: str, result: str) -> dict[str, Any]:
        return {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": tool_call_id, "content": result}],
        }

    def format_assistant_message(self, response: ProviderResponse) -> dict[str, Any]:
        return {"role": "assistant", "content": response.raw.content}
