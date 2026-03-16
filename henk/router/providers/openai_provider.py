from __future__ import annotations

import json
from typing import Any

try:
    import openai
except ModuleNotFoundError:
    from henk._stubs import openai

from henk.router.providers.base import (
    BaseProvider,
    ProviderRequestError,
    ProviderResponse,
    ToolCall,
    classify_provider_error,
)


class OpenAICompatibleProvider(BaseProvider):
    name = "openai-compatible"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str | None = None,
        max_tokens_param: str = "max_tokens",
    ):
        if base_url:
            self._client = openai.OpenAI(api_key=api_key, base_url=base_url)
        else:
            self._client = openai.OpenAI(api_key=api_key)
        self._model = model
        self._max_tokens_param = max_tokens_param

    def chat(
        self,
        messages: list[dict[str, Any]],
        system: str,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 1024,
    ) -> ProviderResponse:
        openai_messages = messages.copy()
        if system:
            openai_messages = [{"role": "system", "content": system}] + openai_messages
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": openai_messages,
        }
        kwargs[self._max_tokens_param] = max_tokens
        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        try:
            response = self._client.chat.completions.create(**kwargs)
        except Exception as error:
            raise ProviderRequestError(self.name, classify_provider_error(error), str(error)) from error
        choice = response.choices[0]
        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
        output_tokens = getattr(usage, "completion_tokens", 0) if usage else 0

        if choice.message.tool_calls:
            tool_calls = [
                ToolCall(
                    id=tool_call.id,
                    name=tool_call.function.name,
                    parameters=json.loads(tool_call.function.arguments),
                )
                for tool_call in choice.message.tool_calls
            ]
            return ProviderResponse(
                text=None,
                tool_calls=tool_calls,
                raw=response,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

        return ProviderResponse(
            text=choice.message.content,
            tool_calls=None,
            raw=response,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    def supports_tools(self) -> bool:
        return True

    def format_tool_result(self, tool_call_id: str, result: str) -> dict[str, Any]:
        return {"role": "tool", "tool_call_id": tool_call_id, "content": result}

    def format_assistant_message(self, response: ProviderResponse) -> dict[str, Any]:
        msg = response.raw.choices[0].message
        payload: dict[str, Any] = {"role": "assistant", "content": msg.content}
        if msg.tool_calls:
            payload["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ]
        return payload

    def _convert_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["input_schema"],
                },
            }
            for tool in tools
        ]


class OpenAIProvider(OpenAICompatibleProvider):
    name = "openai"

    def __init__(self, api_key: str, model: str):
        super().__init__(api_key=api_key, model=model, max_tokens_param="max_completion_tokens")
