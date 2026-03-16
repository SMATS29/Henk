"""Tests voor de Brain."""

import asyncio
from copy import deepcopy
from unittest.mock import MagicMock

import pytest

from henk.brain import Brain, SYSTEM_PROMPT
from henk.config import Config, DEFAULT_CONFIG
from henk.model_gateway import ModelCallResult
from henk.requirements import Requirements
from henk.router.providers.base import ProviderResponse, ToolCall
from henk.tools.base import ToolResult
from henk.token_tracker import TokenTracker


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


class DummyModelGateway:
    def __init__(self, provider):
        self.provider = provider
        self.calls = []
        self.token_tracker = TokenTracker()

    def chat(self, *, role, messages, system, tools=None, max_tokens=1024, purpose, require_tools=False):
        self.calls.append(
            {
                "role": role,
                "messages": messages,
                "system": system,
                "tools": tools,
                "max_tokens": max_tokens,
                "purpose": purpose,
                "require_tools": require_tools,
            }
        )
        response = self.provider.chat(messages=messages, system=system, tools=tools, max_tokens=max_tokens)
        self.token_tracker.add(getattr(response, "input_tokens", 0), getattr(response, "output_tokens", 0))
        return ModelCallResult(provider=self.provider, response=response)


def _make_config() -> Config:
    data = deepcopy(DEFAULT_CONFIG)
    return Config(data)


def test_brain_skips_identity_prompt_when_disabled():
    provider = DummyProvider([ProviderResponse(text="Hoi!", tool_calls=None, raw=None)])
    brain = Brain(_make_config(), model_gateway=DummyModelGateway(provider))
    asyncio.run(brain.think("hallo"))
    assert provider.calls[0]["system"] == ""


def test_brain_uses_system_prompt_when_enabled():
    provider = DummyProvider([ProviderResponse(text="Hoi!", tool_calls=None, raw=None)])
    config = _make_config()
    config.raw["henk"]["identity_prompt_enabled"] = True
    brain = Brain(config, model_gateway=DummyModelGateway(provider))
    asyncio.run(brain.think("hallo"))
    assert provider.calls[0]["system"] == SYSTEM_PROMPT


def test_brain_builds_message_history():
    provider = DummyProvider([
        ProviderResponse(text="Antwoord 1", tool_calls=None, raw=None),
        ProviderResponse(text="Antwoord 2", tool_calls=None, raw=None),
    ])
    brain = Brain(_make_config(), model_gateway=DummyModelGateway(provider))
    asyncio.run(brain.think("bericht 1"))
    asyncio.run(brain.think("bericht 2"))

    assert provider.calls[1]["messages"] == [
        {"role": "user", "content": "bericht 1"},
        {"role": "assistant", "content": "Antwoord 1"},
        {"role": "user", "content": "bericht 2"},
    ]


def test_brain_appends_memory_context_to_system_prompt():
    provider = DummyProvider([ProviderResponse(text="Hoi!", tool_calls=None, raw=None)])
    retrieval = MagicMock()
    retrieval.get_context.return_value = "Project Henk"

    brain = Brain(_make_config(), model_gateway=DummyModelGateway(provider), memory_retrieval=retrieval)
    asyncio.run(brain.think("status?"))

    system_prompt = provider.calls[0]["system"]
    assert system_prompt == "## Geheugen\nProject Henk"


def test_brain_appends_memory_context_to_system_prompt_with_identity_when_enabled():
    provider = DummyProvider([ProviderResponse(text="Hoi!", tool_calls=None, raw=None)])
    retrieval = MagicMock()
    retrieval.get_context.return_value = "Project Henk"
    config = _make_config()
    config.raw["henk"]["identity_prompt_enabled"] = True

    brain = Brain(config, model_gateway=DummyModelGateway(provider), memory_retrieval=retrieval)
    asyncio.run(brain.think("status?"))

    system_prompt = provider.calls[0]["system"]
    assert SYSTEM_PROMPT in system_prompt
    assert "Project Henk" in system_prompt


def test_run_with_tools_keeps_history_and_returns_final_answer():
    provider = DummyProvider([
        ProviderResponse(text=None, tool_calls=[ToolCall(id="tool-1", name="web_search", parameters={"query": "test"})], raw=None),
        ProviderResponse(text="Klaar", tool_calls=None, raw=None),
    ])
    brain = Brain(_make_config(), model_gateway=DummyModelGateway(provider))

    def executor(name: str, params: dict):
        assert name == "web_search"
        assert params == {"query": "test"}
        return ToolResult(success=True, data="zoekresultaat", source_tag="")

    out = asyncio.run(brain.run_with_tools("zoek iets", executor))
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
    brain = Brain(_make_config(), model_gateway=DummyModelGateway(provider))
    asyncio.run(brain.think("wat deden we?"))
    summary = asyncio.run(brain.summarize_session())

    assert summary == "Samenvatting"
    prompt = provider.calls[1]["messages"][0]["content"]
    assert "Gebruiker: wat deden we?" in prompt
    assert provider.calls[1]["system"] == ""


def test_brain_tracks_tokens_from_provider_responses():
    provider = DummyProvider(
        [
            ProviderResponse(text="a", tool_calls=None, raw=None, input_tokens=10, output_tokens=5),
            ProviderResponse(text="b", tool_calls=None, raw=None, input_tokens=4, output_tokens=3),
        ]
    )
    gateway = DummyModelGateway(provider)
    brain = Brain(_make_config(), model_gateway=gateway)
    asyncio.run(brain.think("eerste"))
    asyncio.run(brain.think("tweede"))

    assert brain.token_tracker.total_input == 14
    assert brain.token_tracker.total_output == 8
    assert brain.token_tracker.total == 22
    assert brain.token_tracker is gateway.token_tracker


def test_brain_routes_all_llm_calls_via_model_gateway():
    provider = DummyProvider([
        ProviderResponse(text="gesprek", tool_calls=None, raw=None),
        ProviderResponse(text="Vraag?", tool_calls=None, raw=None),
        ProviderResponse(text="Samenvatting", tool_calls=None, raw=None),
    ])
    gateway = DummyModelGateway(provider)
    brain = Brain(_make_config(), model_gateway=gateway)
    requirements = Requirements(task_description="maak een plan")

    assert brain.classify_input("hoi") == "gesprek"
    brain.refine_requirements("maak een plan", requirements)
    brain._history = [{"role": "user", "content": "x"}, {"role": "assistant", "content": "y"}]
    asyncio.run(brain.summarize_session())

    assert [call["purpose"] for call in gateway.calls] == [
        "classify_input",
        "refine_requirements",
        "summarize_session",
    ]
