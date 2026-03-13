from __future__ import annotations

import os
from enum import Enum
from typing import Any

from urllib.error import URLError
from urllib.request import urlopen

from henk.config import Config
from henk.router.providers import (
    AnthropicProvider,
    BaseProvider,
    DeepSeekProvider,
    LMStudioProvider,
    OllamaProvider,
    OpenAIProvider,
)


class ModelRole(str, Enum):
    FAST = "fast"
    DEFAULT = "default"
    HEAVY = "heavy"


class ModelRouter:
    def __init__(self, config: Config):
        self._config = config
        self._providers: dict[str, BaseProvider] = {}
        self._role_mapping: dict[ModelRole, list[str]] = {}
        self._provider_meta: dict[str, dict[str, Any]] = {}
        self._initialize()

    def _initialize(self) -> None:
        self._providers = {}
        self._provider_meta = {}

        for role in ModelRole:
            role_cfg = self._config.roles_config.get(role.value, {})
            chain: list[str] = []
            for provider_model in [role_cfg.get("primary")] + list(role_cfg.get("fallback", [])):
                if not provider_model:
                    continue
                key = provider_model
                chain.append(key)
                if key in self._providers:
                    continue
                provider_name, model = self._split_provider_model(provider_model)
                provider = self._build_provider(provider_name, model)
                self._providers[key] = provider
                provider_cfg = self._config.providers_config.get(provider_name, {})
                self._provider_meta[key] = {
                    "provider": provider_name,
                    "model": model,
                    "base_url": provider_cfg.get("base_url"),
                    "api_key_env": provider_cfg.get("api_key_env"),
                }
            self._role_mapping[role] = chain

    def _split_provider_model(self, provider_model: str) -> tuple[str, str]:
        provider, _, model = provider_model.partition("/")
        if not provider or not model:
            raise RuntimeError(f"Ongeldige provider/model configuratie: {provider_model}")
        return provider, model

    def _build_provider(self, provider_name: str, model: str) -> BaseProvider:
        cfg = self._config.providers_config.get(provider_name, {})
        if provider_name == "anthropic":
            return AnthropicProvider(api_key=os.environ.get(cfg.get("api_key_env", ""), ""), model=model)
        if provider_name == "openai":
            return OpenAIProvider(api_key=os.environ.get(cfg.get("api_key_env", ""), ""), model=model)
        if provider_name == "ollama":
            return OllamaProvider(model=model, base_url=cfg.get("base_url", "http://localhost:11434/v1"))
        if provider_name == "lmstudio":
            return LMStudioProvider(model=model, base_url=cfg.get("base_url", "http://localhost:1234/v1"))
        if provider_name == "deepseek":
            return DeepSeekProvider(api_key=os.environ.get(cfg.get("api_key_env", ""), ""), model=model)
        raise RuntimeError(f"Onbekende provider: {provider_name}")

    def get_provider(self, role: ModelRole = ModelRole.DEFAULT, *, require_tools: bool = False) -> BaseProvider:
        providers_for_role = self._role_mapping.get(role, [])
        for provider_key in providers_for_role:
            provider = self._providers.get(provider_key)
            if not provider:
                continue
            if require_tools and not provider.supports_tools():
                continue
            if self._is_available(provider_key, provider):
                return provider
        raise RuntimeError(f"Geen beschikbare provider voor rol: {role.value}")

    def _is_available(self, provider_key: str, provider: BaseProvider) -> bool:
        meta = self._provider_meta.get(provider_key, {})
        provider_name = meta.get("provider", provider.name)
        if provider_name in {"anthropic", "openai", "deepseek"}:
            api_key_env = meta.get("api_key_env")
            return bool(api_key_env and os.environ.get(api_key_env))
        base_url = meta.get("base_url")
        if not base_url:
            return True
        try:
            with urlopen(base_url.removesuffix("/v1") + "/", timeout=0.5):
                return True
        except URLError:
            return False

    def describe_role_chain(self, role: ModelRole) -> list[str]:
        return list(self._role_mapping.get(role, []))

    def provider_label(self, provider: BaseProvider) -> str:
        model = getattr(provider, "_model", "")
        return f"{provider.name}/{model}" if model else provider.name

    def list_providers(self) -> dict[str, str]:
        return {
            key: ("beschikbaar" if self._is_available(key, provider) else "onbeschikbaar")
            for key, provider in self._providers.items()
        }
