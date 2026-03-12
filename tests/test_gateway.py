"""Tests voor de Gateway."""

import json

import pytest

from henk.tools.base import ToolResult
from henk.gateway import Gateway, KillSwitchActive
from henk.transcript import TranscriptWriter


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
    react_loop.run.assert_called_once_with("test bericht")


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
