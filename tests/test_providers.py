from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from henk.router.providers.anthropic import AnthropicProvider
from henk.router.providers.deepseek import DeepSeekProvider
from henk.router.providers.lmstudio import LMStudioProvider
from henk.router.providers.ollama import OllamaProvider
from henk.router.providers.openai_provider import OpenAICompatibleProvider


@patch("henk.router.providers.anthropic.anthropic.Anthropic")
def test_anthropic_provider_formats_tool_calls(mock_cls):
    mock_client = MagicMock()
    mock_cls.return_value = mock_client
    block = SimpleNamespace(type="tool_use", id="1", name="web_search", input={"q": "x"})
    mock_client.messages.create.return_value = SimpleNamespace(content=[block])

    provider = AnthropicProvider(api_key="x", model="m")
    response = provider.chat(messages=[{"role": "user", "content": "h"}], system="s")

    assert response.tool_calls[0].name == "web_search"
    formatted = provider.format_assistant_message(response)
    assert formatted["role"] == "assistant"


@patch("henk.router.providers.openai_provider.openai.OpenAI")
def test_openai_compatible_tool_conversion_and_message_format(mock_openai):
    mock_client = MagicMock()
    mock_openai.return_value = mock_client
    tool_call = SimpleNamespace(
        id="tc-1",
        function=SimpleNamespace(name="x", arguments='{"a":1}'),
    )
    msg = SimpleNamespace(content=None, tool_calls=[tool_call])
    mock_client.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(message=msg)])

    provider = OpenAICompatibleProvider(api_key="k", model="m")
    response = provider.chat(
        messages=[{"role": "user", "content": "h"}],
        system="s",
        tools=[{"name": "x", "description": "d", "input_schema": {"type": "object"}}],
    )
    assert response.tool_calls[0].parameters == {"a": 1}
    formatted = provider.format_assistant_message(response)
    assert formatted["tool_calls"][0]["function"]["name"] == "x"


def test_openai_compatible_subclasses_have_expected_names():
    assert OllamaProvider(model="m").name == "ollama"
    assert LMStudioProvider(model="m").name == "lmstudio"
    assert DeepSeekProvider(api_key="k", model="m").name == "deepseek"
