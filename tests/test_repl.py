import pytest

prompt_toolkit = pytest.importorskip("prompt_toolkit")
Document = prompt_toolkit.document.Document

from copy import deepcopy

from henk.config import Config, DEFAULT_CONFIG
from henk.repl import (
    SlashCommandAutoSuggest,
    _build_completer,
    _build_key_bindings,
    _message_for_model_error,
    _startup_missing_key_message,
)
from henk.router import ModelRole, ProviderAttempt, ProviderSelectionError
from henk.router.router import ModelRouter
from henk.router.providers.base import ProviderRequestError


def test_completer_suggests_for_slash_prefix():
    completer = _build_completer()
    completions = list(completer.get_completions(Document(text="/st", cursor_position=3), None))
    texts = [item.text for item in completions]
    assert "/status" in texts
    assert "/stop" in texts


def test_completer_ignores_plain_text():
    completer = _build_completer()
    completions = list(completer.get_completions(Document(text="hallo", cursor_position=5), None))
    assert completions == []


def test_message_for_missing_credentials_error():
    error = ProviderSelectionError(
        ModelRole.DEFAULT,
        [ProviderAttempt("openai/gpt-5.2", "missing_credentials")],
    )

    assert _message_for_model_error(error) == "Ik kan geen model bereiken omdat er geen API key is ingesteld."


def test_message_for_provider_network_error():
    error = ProviderRequestError("openai", "network_unavailable", "connection refused")

    assert _message_for_model_error(error) == "Ik kan het model nu niet bereiken. Check je internet of lokale modelserver."


def test_build_key_bindings_remains_compatible():
    bindings, shift_enter_supported = _build_key_bindings()

    assert bindings is not None
    assert isinstance(shift_enter_supported, bool)


def test_slash_command_auto_suggest_returns_suffix():
    suggestion = SlashCommandAutoSuggest().get_suggestion(None, Document(text="/c", cursor_position=2))

    assert suggestion is not None
    assert suggestion.text == "lear"


def test_slash_command_auto_suggest_ignores_plain_text():
    suggestion = SlashCommandAutoSuggest().get_suggestion(None, Document(text="hallo", cursor_position=5))

    assert suggestion is None


def test_startup_missing_key_message_lists_roles(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    data = deepcopy(DEFAULT_CONFIG)
    data["roles"]["fast"] = {"primary": "openai/gpt-5-mini", "fallback": []}
    data["roles"]["default"] = {"primary": "openai/gpt-5.2", "fallback": []}
    data["roles"]["heavy"] = {"primary": "openai/gpt-5.2", "fallback": []}
    router = ModelRouter(Config(data))

    message = _startup_missing_key_message(router)

    assert message == "Ik heb nog geen API keys beschikbaar voor de volgende modellen: fast, default en heavy."
