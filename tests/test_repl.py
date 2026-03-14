import pytest

prompt_toolkit = pytest.importorskip("prompt_toolkit")
Document = prompt_toolkit.document.Document

from henk.repl import _build_completer, _message_for_model_error
from henk.router import ModelRole, ProviderAttempt, ProviderSelectionError
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
        [ProviderAttempt("openai/gpt-4o", "missing_credentials")],
    )

    assert _message_for_model_error(error) == "Ik kan geen model bereiken omdat er geen API key is ingesteld."


def test_message_for_provider_network_error():
    error = ProviderRequestError("openai", "network_unavailable", "connection refused")

    assert _message_for_model_error(error) == "Ik kan het model nu niet bereiken. Check je internet of lokale modelserver."
