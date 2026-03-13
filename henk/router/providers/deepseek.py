from __future__ import annotations

from henk.router.providers.openai_provider import OpenAICompatibleProvider


class DeepSeekProvider(OpenAICompatibleProvider):
    name = "deepseek"

    def __init__(self, api_key: str, model: str):
        super().__init__(api_key=api_key, model=model, base_url="https://api.deepseek.com")
