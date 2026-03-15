import pytest

from copy import deepcopy

from henk.config import Config, DEFAULT_CONFIG
from henk.router.router import ModelRole, ModelRouter, ProviderAttempt, ProviderSelectionError


def _cfg():
    data = deepcopy(DEFAULT_CONFIG)
    data["providers"]["ollama"]["base_url"] = "http://localhost:9/v1"
    data["roles"]["fast"] = {
        "primary": "ollama/qwen2.5:3b",
        "fallback": ["openai/gpt-5-mini"],
    }
    return Config(data)


def test_router_selects_provider_with_fallback_when_unavailable(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "key")
    router = ModelRouter(_cfg())
    provider = router.get_provider(ModelRole.FAST)
    assert provider.name == "openai"


def test_router_selection_error_without_available_provider(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    data = deepcopy(DEFAULT_CONFIG)
    data["roles"]["default"] = {"primary": "openai/gpt-5.2", "fallback": ["openai/gpt-5-mini"]}
    router = ModelRouter(Config(data))

    with pytest.raises(ProviderSelectionError) as exc_info:
        router.get_provider(ModelRole.DEFAULT)

    assert exc_info.value.reasons == {"missing_credentials"}


def test_router_selection_error_marks_unavailable_local_provider():
    data = deepcopy(DEFAULT_CONFIG)
    data["providers"]["ollama"]["base_url"] = "http://localhost:9/v1"
    data["roles"]["fast"] = {"primary": "ollama/qwen2.5:3b", "fallback": []}
    router = ModelRouter(Config(data))

    with pytest.raises(ProviderSelectionError) as exc_info:
        router.get_provider(ModelRole.FAST)

    assert exc_info.value.attempts == [ProviderAttempt("ollama/qwen2.5:3b", "provider_unavailable")]


def test_router_list_providers_status(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "key")
    router = ModelRouter(_cfg())
    statuses = router.list_providers()
    assert "openai/gpt-5-mini" in statuses
