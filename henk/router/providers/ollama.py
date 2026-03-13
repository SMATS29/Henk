from __future__ import annotations

from henk.router.providers.openai_provider import OpenAICompatibleProvider


class OllamaProvider(OpenAICompatibleProvider):
    name = "ollama"

    def __init__(self, model: str, base_url: str = "http://localhost:11434/v1"):
        super().__init__(api_key="ollama", model=model, base_url=base_url)
