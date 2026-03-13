from __future__ import annotations

from henk.router.providers.openai_provider import OpenAICompatibleProvider


class LMStudioProvider(OpenAICompatibleProvider):
    name = "lmstudio"

    def __init__(self, model: str, base_url: str = "http://localhost:1234/v1"):
        super().__init__(api_key="lmstudio", model=model, base_url=base_url)
