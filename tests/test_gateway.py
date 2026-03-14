"""Tests voor de Gateway."""

import json

import pytest

from henk.tools.base import ToolResult
from henk.gateway import Gateway, KillSwitchActive
from henk.model_gateway import ModelGateway
from henk.router import ModelRole, ProviderAttempt, ProviderSelectionError
from henk.router.providers.base import ProviderResponse
from henk.transcript import TranscriptWriter


def test_gateway_returns_local_greeting_with_user_name(config, mock_brain):
    """Gateway gebruikt een lokale startup-groet met naam uit config."""
    config.raw["henk"]["user_name"] = "Joost"
    transcript = TranscriptWriter(config.logs_dir)
    gateway = Gateway(config, mock_brain, transcript)

    greeting = gateway.get_greeting()

    assert greeting == "Hoi, Joost. Zeg het maar."
    assert mock_brain.mock_calls == []
    content = transcript.file_path.read_text(encoding="utf-8")
    assert "Hoi, Joost. Zeg het maar." in content


def test_gateway_returns_local_greeting_without_user_name(config, mock_brain):
    transcript = TranscriptWriter(config.logs_dir)
    gateway = Gateway(config, mock_brain, transcript)

    greeting = gateway.get_greeting()

    assert greeting == "Hoi. Zeg het maar."
    assert mock_brain.mock_calls == []


def test_gateway_blocks_on_hard_stop(config, mock_brain):
    """Gateway blokkeert bij actieve hard_stop."""
    (config.control_dir / "hard_stop").write_text("true", encoding="utf-8")

    transcript = TranscriptWriter(config.logs_dir)
    gateway = Gateway(config, mock_brain, transcript)

    with pytest.raises(KillSwitchActive) as exc_info:
        gateway.process("hallo")
    assert exc_info.value.switch_type == "hard_stop"


def test_gateway_blocks_on_graceful_stop(config, mock_brain):
    """Gateway blokkeert bij actieve graceful_stop."""
    (config.control_dir / "graceful_stop").write_text("true", encoding="utf-8")

    transcript = TranscriptWriter(config.logs_dir)
    gateway = Gateway(config, mock_brain, transcript)

    with pytest.raises(KillSwitchActive) as exc_info:
        gateway.process("hallo")
    assert exc_info.value.switch_type == "graceful_stop"


def test_gateway_passes_message_to_brain_without_react_loop(config, mock_brain):
    """Gateway stuurt berichten door naar Brain als geen loop is gezet."""
    transcript = TranscriptWriter(config.logs_dir)
    gateway = Gateway(config, mock_brain, transcript)

    response = gateway.process("test bericht")
    assert response == "Test antwoord van Henk."
    mock_brain.think.assert_called_once_with("test bericht")


def test_gateway_uses_react_loop_when_set(config, mock_brain):
    """Gateway routeert berichten via ReactLoop als die gekoppeld is."""
    transcript = TranscriptWriter(config.logs_dir)
    gateway = Gateway(config, mock_brain, transcript)
    react_loop = mock_brain
    react_loop.run.return_value = "Via loop"

    gateway.set_react_loop(react_loop)
    response = gateway.process("test bericht")

    assert response == "Via loop"
    react_loop.run.assert_called_once_with("test bericht", on_status=None)


def test_gateway_ignores_empty_input(config, mock_brain):
    """Gateway negeert lege berichten."""
    transcript = TranscriptWriter(config.logs_dir)
    gateway = Gateway(config, mock_brain, transcript)

    response = gateway.process("")
    assert response == ""
    mock_brain.think.assert_not_called()


def test_gateway_logs_messages(config, mock_brain):
    """Gateway logt berichten via transcript."""
    transcript = TranscriptWriter(config.logs_dir)
    gateway = Gateway(config, mock_brain, transcript)

    gateway.process("hallo Henk")

    # Controleer dat het transcript bestand bestaat en inhoud heeft
    assert transcript.file_path.exists()
    content = transcript.file_path.read_text(encoding="utf-8")
    assert "hallo Henk" in content
    assert "Test antwoord van Henk." in content


def test_gateway_masks_memory_write_payload(config, mock_brain):
    transcript = TranscriptWriter(config.logs_dir)
    gateway = Gateway(config, mock_brain, transcript)

    gateway.log_tool_result("memory_write", ToolResult(success=True, data="gevoelige payload", source_tag="[TOOL:memory_write]"))

    last_record = transcript.file_path.read_text(encoding="utf-8").strip().splitlines()[-1]
    payload = json.loads(last_record)["payload"]
    assert payload == "[MEMORY — niet gelogd]"


class DummyProvider:
    name = "dummy"
    _model = "m"

    def __init__(self, response: ProviderResponse):
        self._response = response

    def chat(self, **kwargs):
        return self._response

    def supports_tools(self):
        return True


class DummyRouter:
    def __init__(self, provider):
        self._provider = provider
        self.calls = []

    def get_provider(self, role=ModelRole.DEFAULT, require_tools=False):
        self.calls.append((role, require_tools))
        return self._provider

    def provider_label(self, provider):
        return f"{provider.name}/{provider._model}"


class FailingRouter:
    def get_provider(self, role=ModelRole.DEFAULT, require_tools=False):
        raise ProviderSelectionError(role, [ProviderAttempt("openai/gpt-4o", "missing_credentials")])

    def provider_label(self, provider):
        return "n/a"


def test_model_gateway_tracks_calls_and_tokens(config):
    provider = DummyProvider(ProviderResponse(text="Hoi", tool_calls=None, raw=None, input_tokens=12, output_tokens=7))
    transcript = TranscriptWriter(config.logs_dir)
    model_gateway = ModelGateway(DummyRouter(provider), transcript)

    result = model_gateway.chat(
        role=ModelRole.DEFAULT,
        messages=[{"role": "user", "content": "hallo"}],
        system="s",
        purpose="think",
    )

    assert result.response.text == "Hoi"
    assert model_gateway.call_count == 1
    assert model_gateway.token_tracker.total_input == 12
    assert model_gateway.token_tracker.total_output == 7


def test_model_gateway_logs_debug_events_to_transcript(config):
    provider = DummyProvider(ProviderResponse(text="Hoi", tool_calls=None, raw=None, input_tokens=3, output_tokens=2))
    transcript = TranscriptWriter(config.logs_dir)
    model_gateway = ModelGateway(DummyRouter(provider), transcript)

    model_gateway.chat(
        role=ModelRole.FAST,
        messages=[{"role": "user", "content": "classificeer"}],
        system="s",
        purpose="classify_input",
    )

    records = [json.loads(line) for line in transcript.file_path.read_text(encoding="utf-8").splitlines()]
    assert records[-2]["type"] == "model.request"
    assert records[-2]["purpose"] == "classify_input"
    assert records[-1]["type"] == "model.response"
    assert records[-1]["provider"] == "dummy/m"


def test_model_gateway_logs_error_events_to_transcript(config):
    transcript = TranscriptWriter(config.logs_dir)
    model_gateway = ModelGateway(FailingRouter(), transcript)

    with pytest.raises(ProviderSelectionError):
        model_gateway.chat(
            role=ModelRole.DEFAULT,
            messages=[{"role": "user", "content": "hallo"}],
            system="s",
            purpose="think",
        )

    record = json.loads(transcript.file_path.read_text(encoding="utf-8").splitlines()[-1])
    assert record["type"] == "model.error"
    assert record["reason"] == "selection_failed"
    assert record["attempts"][0]["reason"] == "missing_credentials"
