"""Tests voor de Gateway."""

import asyncio
import json

import pytest

from unittest.mock import AsyncMock, MagicMock

from henk.tools.base import ToolResult
from henk.gateway import Gateway, KillSwitchActive, RunStatus
from henk.model_gateway import ModelGateway
from henk.router import ModelRole, ProviderAttempt, ProviderSelectionError
from henk.router.providers.base import ProviderRequestError, ProviderResponse
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
        asyncio.run(gateway.process("hallo"))
    assert exc_info.value.switch_type == "hard_stop"


def test_gateway_blocks_on_graceful_stop(config, mock_brain):
    """Gateway blokkeert bij actieve graceful_stop."""
    (config.control_dir / "graceful_stop").write_text("true", encoding="utf-8")

    transcript = TranscriptWriter(config.logs_dir)
    gateway = Gateway(config, mock_brain, transcript)

    with pytest.raises(KillSwitchActive) as exc_info:
        asyncio.run(gateway.process("hallo"))
    assert exc_info.value.switch_type == "graceful_stop"


def test_gateway_passes_message_to_brain_without_react_loop(config, mock_brain):
    """Gateway stuurt berichten door naar Brain als geen loop is gezet."""
    transcript = TranscriptWriter(config.logs_dir)
    gateway = Gateway(config, mock_brain, transcript)

    mock_brain.think = AsyncMock(return_value="Test antwoord van Henk.")
    response = asyncio.run(gateway.process("test bericht"))
    assert response == "Test antwoord van Henk."
    mock_brain.think.assert_called_once_with("test bericht")


def test_gateway_uses_react_loop_when_set(config, mock_brain):
    """Gateway routeert berichten via ReactLoop als die gekoppeld is."""
    transcript = TranscriptWriter(config.logs_dir)
    gateway = Gateway(config, mock_brain, transcript)
    react_loop = MagicMock()
    react_loop.run = AsyncMock(return_value="Via loop")

    gateway.set_react_loop(react_loop)
    response = asyncio.run(gateway.process("test bericht"))

    assert response == "Via loop"
    react_loop.run.assert_called_once_with("test bericht", on_status=None)


def test_gateway_ignores_empty_input(config, mock_brain):
    """Gateway negeert lege berichten."""
    transcript = TranscriptWriter(config.logs_dir)
    gateway = Gateway(config, mock_brain, transcript)

    response = asyncio.run(gateway.process(""))
    assert response == ""
    mock_brain.think.assert_not_called()


def test_gateway_logs_messages(config, mock_brain):
    """Gateway logt berichten via transcript."""
    transcript = TranscriptWriter(config.logs_dir)
    gateway = Gateway(config, mock_brain, transcript)

    mock_brain.think = AsyncMock(return_value="Test antwoord van Henk.")
    asyncio.run(gateway.process("hallo Henk"))

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


class CandidateRouter(DummyRouter):
    def __init__(self, providers):
        self._providers = providers
        self.calls = []

    def get_provider_candidates(self, role=ModelRole.DEFAULT, require_tools=False):
        self.calls.append((role, require_tools))
        return self._providers


class FailingRouter:
    def get_provider(self, role=ModelRole.DEFAULT, require_tools=False):
        raise ProviderSelectionError(role, [ProviderAttempt("openai/gpt-5.2", "missing_credentials")])

    def provider_label(self, provider):
        return "n/a"


class FailingProvider(DummyProvider):
    def __init__(self, reason: str, detail: str = "fout"):
        self._reason = reason
        self._detail = detail
        self._model = "m"

    def chat(self, **kwargs):
        raise ProviderRequestError("dummy", self._reason, self._detail)


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


def test_model_gateway_retries_with_fallback_provider(config):
    transcript = TranscriptWriter(config.logs_dir)
    providers = [
        FailingProvider("model_unavailable", "model does not exist"),
        DummyProvider(ProviderResponse(text="Via fallback", tool_calls=None, raw=None, input_tokens=5, output_tokens=2)),
    ]
    model_gateway = ModelGateway(CandidateRouter(providers), transcript)

    result = model_gateway.chat(
        role=ModelRole.DEFAULT,
        messages=[{"role": "user", "content": "hallo"}],
        system="s",
        purpose="think",
    )

    assert result.response.text == "Via fallback"
    assert model_gateway.call_count == 2
    records = [json.loads(line) for line in transcript.file_path.read_text(encoding="utf-8").splitlines()]
    assert records[-3]["type"] == "model.error"
    assert records[-3]["retrying_with_fallback"] is True
    assert records[-1]["type"] == "model.response"


# --- Token tracking & run lifecycle tests ---


def test_start_run_creates_run_state(config, mock_brain):
    transcript = TranscriptWriter(config.logs_dir)
    gateway = Gateway(config, mock_brain, transcript)

    run_id = gateway.start_run("Analyseer Q3-rapport voor Joost")

    assert run_id is not None
    assert run_id.startswith("run_")
    tasks = gateway.get_task_state()
    assert len(tasks) == 1
    assert tasks[0].run_id == run_id
    assert tasks[0].summary == "Analyseer Q3-rapport voor Joost"
    assert tasks[0].status == RunStatus.ACTIVE
    assert tasks[0].tokens_input == 0
    assert tasks[0].tokens_output == 0


def test_start_run_truncates_summary_at_80_chars(config, mock_brain):
    transcript = TranscriptWriter(config.logs_dir)
    gateway = Gateway(config, mock_brain, transcript)

    long_summary = "x" * 120
    gateway.start_run(long_summary)

    tasks = gateway.get_task_state()
    assert len(tasks[0].summary) == 80


def test_complete_run_sets_done_status(config, mock_brain):
    transcript = TranscriptWriter(config.logs_dir)
    gateway = Gateway(config, mock_brain, transcript)

    run_id = gateway.start_run("test taak")
    gateway.complete_run(run_id)

    tasks = gateway.get_task_state()
    assert tasks[0].status == RunStatus.DONE
    assert tasks[0].ended_at is not None


def test_fail_run_sets_failed_status(config, mock_brain):
    transcript = TranscriptWriter(config.logs_dir)
    gateway = Gateway(config, mock_brain, transcript)

    run_id = gateway.start_run("test taak")
    gateway.fail_run(run_id)

    tasks = gateway.get_task_state()
    assert tasks[0].status == RunStatus.FAILED
    assert tasks[0].ended_at is not None


def test_record_token_usage_accumulates_per_run(config, mock_brain):
    transcript = TranscriptWriter(config.logs_dir)
    gateway = Gateway(config, mock_brain, transcript)

    run_id = gateway.start_run("test taak")
    gateway.record_token_usage(100, 50)
    gateway.record_token_usage(200, 80)

    tasks = gateway.get_task_state()
    assert tasks[0].tokens_input == 300
    assert tasks[0].tokens_output == 130


def test_record_token_usage_accumulates_session_totals(config, mock_brain):
    transcript = TranscriptWriter(config.logs_dir)
    gateway = Gateway(config, mock_brain, transcript)

    run_id = gateway.start_run("taak 1")
    gateway.record_token_usage(100, 50)
    gateway.complete_run(run_id)

    run_id2 = gateway.start_run("taak 2")
    gateway.record_token_usage(200, 80)

    assert gateway.session_tokens_input == 300
    assert gateway.session_tokens_output == 130
    assert gateway.session_tokens_total == 430


def test_record_token_usage_without_active_run(config, mock_brain):
    transcript = TranscriptWriter(config.logs_dir)
    gateway = Gateway(config, mock_brain, transcript)

    gateway.record_token_usage(100, 50)

    assert gateway.session_tokens_input == 100
    assert gateway.session_tokens_output == 50
    assert gateway.get_task_state() == []


def test_record_token_usage_ignores_negative(config, mock_brain):
    transcript = TranscriptWriter(config.logs_dir)
    gateway = Gateway(config, mock_brain, transcript)

    gateway.record_token_usage(-10, 50)
    gateway.record_token_usage(10, -50)

    assert gateway.session_tokens_total == 0


def test_record_token_usage_logs_brain_token_usage_event(config, mock_brain):
    transcript = TranscriptWriter(config.logs_dir)
    gateway = Gateway(config, mock_brain, transcript)

    run_id = gateway.start_run("test")
    gateway.record_token_usage(100, 50)

    records = [json.loads(line) for line in transcript.file_path.read_text(encoding="utf-8").splitlines()]
    token_events = [r for r in records if r.get("type") == "brain.token_usage"]
    assert len(token_events) == 1
    assert token_events[0]["run_id"] == run_id
    assert token_events[0]["tokens_input"] == 100
    assert token_events[0]["tokens_output"] == 50


def test_get_task_state_returns_frozen_snapshots(config, mock_brain):
    transcript = TranscriptWriter(config.logs_dir)
    gateway = Gateway(config, mock_brain, transcript)

    gateway.start_run("taak 1")
    gateway.record_token_usage(100, 50)
    tasks = gateway.get_task_state()

    # Wijzigen van originele state mag geen effect hebben op snapshot
    gateway.record_token_usage(200, 100)
    assert tasks[0].tokens_input == 100


def test_model_gateway_fires_token_callback(config):
    provider = DummyProvider(ProviderResponse(text="Hoi", tool_calls=None, raw=None, input_tokens=12, output_tokens=7))
    transcript = TranscriptWriter(config.logs_dir)
    model_gateway = ModelGateway(DummyRouter(provider), transcript)

    received = []
    model_gateway.on_token_usage = lambda inp, out: received.append((inp, out))

    model_gateway.chat(
        role=ModelRole.DEFAULT,
        messages=[{"role": "user", "content": "hallo"}],
        system="s",
        purpose="think",
    )

    assert received == [(12, 7)]
