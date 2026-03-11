"""Tests voor de Brain."""

from copy import deepcopy
from unittest.mock import MagicMock, patch

from henk.brain import Brain, SYSTEM_PROMPT
from henk.config import Config, DEFAULT_CONFIG


def _make_anthropic_response(text: str):
    """Maak een mock Anthropic API response."""
    response = MagicMock()
    block = MagicMock()
    block.text = text
    response.content = [block]
    return response


def _make_config(*, provider: str, model: str) -> Config:
    """Maak een testconfig met een expliciete provider."""
    data = deepcopy(DEFAULT_CONFIG)
    data["provider"]["default"] = provider
    data["provider"]["model"] = model
    return Config(data)


@patch("henk.brain.anthropic.Anthropic")
def test_brain_uses_system_prompt(mock_anthropic_cls):
    """Brain stuurt system prompt mee naar Anthropic."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_anthropic_response("Hoi!")
    mock_anthropic_cls.return_value = mock_client

    config = _make_config(provider="anthropic", model="claude-sonnet-4-6")
    brain = Brain(config)
    brain.think("hallo")

    call_kwargs = mock_client.messages.create.call_args
    assert call_kwargs.kwargs["system"] == SYSTEM_PROMPT


@patch("henk.brain.anthropic.Anthropic")
def test_brain_builds_message_history(mock_anthropic_cls):
    """Brain bouwt conversatiegeschiedenis correct op."""
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = [
        _make_anthropic_response("Antwoord 1"),
        _make_anthropic_response("Antwoord 2"),
    ]
    mock_anthropic_cls.return_value = mock_client

    config = _make_config(provider="anthropic", model="claude-sonnet-4-6")
    brain = Brain(config)
    brain.think("bericht 1")
    brain.think("bericht 2")

    second_call = mock_client.messages.create.call_args_list[1]
    messages = second_call.kwargs["messages"]
    assert len(messages) == 3
    assert messages[0] == {"role": "user", "content": "bericht 1"}
    assert messages[1] == {"role": "assistant", "content": "Antwoord 1"}
    assert messages[2] == {"role": "user", "content": "bericht 2"}


@patch("henk.brain.anthropic.Anthropic")
def test_brain_greet_not_in_history(mock_anthropic_cls):
    """Brain.greet() voegt de begroeting niet toe aan de geschiedenis."""
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = [
        _make_anthropic_response("Hoi daar!"),
        _make_anthropic_response("Antwoord"),
    ]
    mock_anthropic_cls.return_value = mock_client

    config = _make_config(provider="anthropic", model="claude-sonnet-4-6")
    brain = Brain(config)
    brain.greet()
    brain.think("vraag")

    second_call = mock_client.messages.create.call_args_list[1]
    messages = second_call.kwargs["messages"]
    assert len(messages) == 1
    assert messages[0] == {"role": "user", "content": "vraag"}


@patch("henk.brain.openai.OpenAI")
def test_brain_uses_openai_responses_for_gpt5_mini(mock_openai_cls):
    """OpenAI provider gebruikt Responses API met GPT-5 mini."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.output_text = "Hoi!"
    mock_client.responses.create.return_value = mock_response
    mock_openai_cls.return_value = mock_client

    config = Config(deepcopy(DEFAULT_CONFIG))
    brain = Brain(config)
    brain.think("hallo")

    call_kwargs = mock_client.responses.create.call_args.kwargs
    assert call_kwargs["model"] == "gpt-5-mini"
    assert call_kwargs["instructions"] == SYSTEM_PROMPT
    assert "Gebruiker: hallo" in call_kwargs["input"]
