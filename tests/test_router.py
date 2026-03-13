from copy import deepcopy

from henk.config import Config, DEFAULT_CONFIG
from henk.router.router import ModelRole, ModelRouter


def _cfg():
    data = deepcopy(DEFAULT_CONFIG)
    data["providers"]["ollama"]["base_url"] = "http://localhost:9/v1"
    data["roles"]["fast"] = {
        "primary": "ollama/qwen2.5:3b",
        "fallback": ["anthropic/claude-haiku-4-5"],
    }
    return Config(data)


def test_router_selects_provider_with_fallback_when_unavailable(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key")
    router = ModelRouter(_cfg())
    provider = router.get_provider(ModelRole.FAST)
    assert provider.name == "anthropic"


def test_router_runtime_error_without_available_provider(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    data = deepcopy(DEFAULT_CONFIG)
    data["roles"]["default"] = {"primary": "openai/gpt-4o", "fallback": ["deepseek/deepseek-chat"]}
    router = ModelRouter(Config(data))
    try:
        router.get_provider(ModelRole.DEFAULT)
        assert False
    except RuntimeError:
        assert True


def test_router_list_providers_status(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key")
    router = ModelRouter(_cfg())
    statuses = router.list_providers()
    assert "anthropic/claude-haiku-4-5" in statuses
