"""Tests voor de Brain."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock

from henk.brain import Brain, SYSTEM_PROMPT
from henk.config import Config, DEFAULT_CONFIG
from henk.router import ModelRole
from henk.router.providers.base import ProviderResponse, ToolCall
from henk.tools.base import ToolResult


class DummyProvider:
    name = "dummy"

    def __init__(self, responses):
        self._responses = responses
        self.calls = []

    def chat(self, messages, system, tools=None, max_tokens=1024):
        self.calls.append({"messages": messages, "system": system, "tools": tools, "max_tokens": max_tokens})
        return self._responses.pop(0)

    def supports_tools(self):
        return True

    def format_assistant_message(self, response):
        return {"role": "assistant", "content": [{"type": "tool_use", "id": "tool-1"}]}

    def format_tool_result(self, tool_call_id, result):
        return {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tool_call_id, "content": result}]}


class DummyRouter:
    def __init__(self, provider):
        self.provider = provider
        self.roles = []

    def get_provider(self, role=ModelRole.DEFAULT, require_tools=False):
        self.roles.append((role, require_tools))
        return self.provider


def _make_config() -> Config:
    data = deepcopy(DEFAULT_CONFIG)
    return Config(data)


def test_brain_uses_system_prompt():
    provider = DummyProvider([ProviderResponse(text="Hoi!", tool_calls=None, raw=None)])
    brain = Brain(_make_config(), router=DummyRouter(provider))
    brain.think("hallo")
    assert provider.calls[0]["system"] == SYSTEM_PROMPT


def test_brain_builds_message_history():
    provider = DummyProvider([
        ProviderResponse(text="Antwoord 1", tool_calls=None, raw=None),
        ProviderResponse(text="Antwoord 2", tool_calls=None, raw=None),
    ])
    brain = Brain(_make_config(), router=DummyRouter(provider))
    brain.think("bericht 1")
    brain.think("bericht 2")

    assert provider.calls[1]["messages"] == [
        {"role": "user", "content": "bericht 1"},
        {"role": "assistant", "content": "Antwoord 1"},
        {"role": "user", "content": "bericht 2"},
    ]


def test_brain_greet_not_in_history():
    provider = DummyProvider([
        ProviderResponse(text="Hoi daar!", tool_calls=None, raw=None),
        ProviderResponse(text="Antwoord", tool_calls=None, raw=None),
    ])
    brain = Brain(_make_config(), router=DummyRouter(provider))
    brain.greet()
    brain.think("vraag")
    assert provider.calls[1]["messages"] == [{"role": "user", "content": "vraag"}]


def test_brain_appends_memory_context_to_system_prompt():
    provider = DummyProvider([ProviderResponse(text="Hoi!", tool_calls=None, raw=None)])
    retrieval = MagicMock()
    retrieval.get_context.return_value = "Project Henk"

    brain = Brain(_make_config(), router=DummyRouter(provider), memory_retrieval=retrieval)
    brain.think("status?")

    system_prompt = provider.calls[0]["system"]
    assert SYSTEM_PROMPT in system_prompt
    assert "Project Henk" in system_prompt


def test_run_with_tools_keeps_history_and_returns_final_answer():
    provider = DummyProvider([
        ProviderResponse(text=None, tool_calls=[ToolCall(id="tool-1", name="web_search", parameters={"query": "test"})], raw=None),
        ProviderResponse(text="Klaar", tool_calls=None, raw=None),
    ])
    brain = Brain(_make_config(), router=DummyRouter(provider))

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


def test_summarize_session_uses_history():
    provider = DummyProvider([
        ProviderResponse(text="Antwoord", tool_calls=None, raw=None),
        ProviderResponse(text="Samenvatting", tool_calls=None, raw=None),
    ])
    brain = Brain(_make_config(), router=DummyRouter(provider))
    brain.think("wat deden we?")
    summary = brain.summarize_session()

    assert summary == "Samenvatting"
    prompt = provider.calls[1]["messages"][0]["content"]
    assert "Gebruiker: wat deden we?" in prompt


def test_brain_tracks_tokens_from_provider_responses():
    provider = DummyProvider(
        [
            ProviderResponse(text="a", tool_calls=None, raw=None, input_tokens=10, output_tokens=5),
            ProviderResponse(text="b", tool_calls=None, raw=None, input_tokens=4, output_tokens=3),
        ]
    )
    brain = Brain(_make_config(), router=DummyRouter(provider))
    brain.think("eerste")
    brain.think("tweede")

    assert brain.token_tracker.total_input == 14
    assert brain.token_tracker.total_output == 8
    assert brain.token_tracker.total == 22
