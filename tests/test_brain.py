"""Tests voor de Brain."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from henk.brain import Brain, SYSTEM_PROMPT
from henk.config import Config, DEFAULT_CONFIG
from henk.tools.base import ToolResult


def _make_anthropic_response(text: str):
    response = MagicMock()
    block = MagicMock()
    block.text = text
    response.content = [block]
    return response


def _make_config(*, provider: str = "anthropic", model: str = "claude-sonnet-4-6") -> Config:
    data = deepcopy(DEFAULT_CONFIG)
    data["provider"]["default"] = provider
    data["provider"]["model"] = model
    return Config(data)


@patch("henk.brain.anthropic.Anthropic")
def test_brain_uses_system_prompt(mock_anthropic_cls):
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_anthropic_response("Hoi!")
    mock_anthropic_cls.return_value = mock_client

    brain = Brain(_make_config())
    brain.think("hallo")

    call_kwargs = mock_client.messages.create.call_args
    assert call_kwargs.kwargs["system"] == SYSTEM_PROMPT


@patch("henk.brain.anthropic.Anthropic")
def test_brain_builds_message_history(mock_anthropic_cls):
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = [
        _make_anthropic_response("Antwoord 1"),
        _make_anthropic_response("Antwoord 2"),
    ]
    mock_anthropic_cls.return_value = mock_client

    brain = Brain(_make_config())
    brain.think("bericht 1")
    brain.think("bericht 2")

    messages = mock_client.messages.create.call_args_list[1].kwargs["messages"]
    assert messages == [
        {"role": "user", "content": "bericht 1"},
        {"role": "assistant", "content": "Antwoord 1"},
        {"role": "user", "content": "bericht 2"},
    ]


@patch("henk.brain.anthropic.Anthropic")
def test_brain_greet_not_in_history(mock_anthropic_cls):
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = [
        _make_anthropic_response("Hoi daar!"),
        _make_anthropic_response("Antwoord"),
    ]
    mock_anthropic_cls.return_value = mock_client

    brain = Brain(_make_config())
    brain.greet()
    brain.think("vraag")

    messages = mock_client.messages.create.call_args_list[1].kwargs["messages"]
    assert messages == [{"role": "user", "content": "vraag"}]


@patch("henk.brain.anthropic.Anthropic")
def test_run_with_tools_keeps_history_and_returns_final_answer(mock_anthropic_cls):
    mock_client = MagicMock()
    tool_block = SimpleNamespace(type="tool_use", id="tool-1", name="web_search", input={"query": "test"})
    final_block = SimpleNamespace(type="text", text="Klaar")
    mock_client.messages.create.side_effect = [
        SimpleNamespace(content=[tool_block]),
        SimpleNamespace(content=[final_block]),
    ]
    mock_anthropic_cls.return_value = mock_client

    brain = Brain(_make_config())

    def executor(name: str, params: dict):
        assert name == "web_search"
        assert params == {"query": "test"}
        return ToolResult(success=True, data="zoekresultaat", source_tag="")

    out = brain.run_with_tools("zoek iets", executor)

    assert out == "Klaar"
    assert brain._history == [
        {"role": "user", "content": "zoek iets"},
        {"role": "assistant", "content": "Klaar"},
    ]

    second_messages = mock_client.messages.create.call_args_list[1].kwargs["messages"]
    assert second_messages[0] == {"role": "user", "content": "zoek iets"}
    assert second_messages[1]["role"] == "assistant"
    assert second_messages[2]["role"] == "user"
