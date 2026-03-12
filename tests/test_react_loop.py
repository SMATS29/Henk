"""Tests voor de ReAct-loop."""

from copy import deepcopy
from unittest.mock import MagicMock

from henk.config import Config, DEFAULT_CONFIG
from henk.gateway import Gateway
from henk.react_loop import ReactLoop
from henk.tools.base import ErrorType, ToolError, ToolResult


class DummyTool:
    parameters = {"required": []}

    def __init__(self, result: ToolResult):
        self._result = result

    def execute(self, **kwargs):
        return self._result


def _make_gateway(tmp_path, max_calls=1):
    data = deepcopy(DEFAULT_CONFIG)
    data["paths"]["workspace_dir"] = str(tmp_path / "workspace")
    data["paths"]["control_dir"] = str(tmp_path / "control")
    data["paths"]["logs_dir"] = str(tmp_path / "logs")
    data["security"]["react_loop"]["max_tool_calls"] = max_calls
    cfg = Config(data)
    cfg.control_dir.mkdir(parents=True, exist_ok=True)
    (cfg.control_dir / "hard_stop").write_text("false", encoding="utf-8")
    (cfg.control_dir / "graceful_stop").write_text("false", encoding="utf-8")
    from henk.transcript import TranscriptWriter

    return Gateway(cfg, MagicMock(), TranscriptWriter(cfg.logs_dir))


def test_loop_stops_after_max_tool_calls(tmp_path):
    brain = MagicMock()
    brain.next_step.side_effect = [
        {"type": "tool_call", "tool_name": "x", "parameters": {}},
        {"type": "tool_call", "tool_name": "x", "parameters": {"a": 1}},
    ]
    gw = _make_gateway(tmp_path, max_calls=1)
    loop = ReactLoop(brain, gw, {"x": DummyTool(ToolResult(True, "ok", "[TOOL:x]"))})

    out = loop.run("hallo")
    assert "tool-limiet" in out


def test_loop_stops_on_identical_call(tmp_path):
    brain = MagicMock()
    brain.next_step.side_effect = [
        {"type": "tool_call", "tool_name": "x", "parameters": {}},
        {"type": "tool_call", "tool_name": "x", "parameters": {}},
    ]
    gw = _make_gateway(tmp_path, max_calls=4)
    loop = ReactLoop(brain, gw, {"x": DummyTool(ToolResult(True, "ok", "[TOOL:x]"))})

    out = loop.run("hallo")
    assert "identieke" in out


def test_loop_stops_on_active_kill_switch(tmp_path):
    brain = MagicMock()
    brain.next_step.return_value = {"type": "tool_call", "tool_name": "x", "parameters": {}}
    gw = _make_gateway(tmp_path, max_calls=4)
    (gw._config.control_dir / "graceful_stop").write_text("true", encoding="utf-8")
    loop = ReactLoop(brain, gw, {"x": DummyTool(ToolResult(True, "ok", "[TOOL:x]"))})

    out = loop.run("hallo")
    assert "kill switch" in out


def test_content_error_counts_against_limit(tmp_path):
    brain = MagicMock()
    brain.next_step.side_effect = [
        {"type": "tool_call", "tool_name": "x", "parameters": {}},
        {"type": "tool_call", "tool_name": "x", "parameters": {"k": 1}},
        {"type": "final", "content": "klaar"},
    ]
    gw = _make_gateway(tmp_path, max_calls=4)
    gw._config.raw["security"]["react_loop"]["max_retries_content"] = 0
    err = ToolResult(False, None, "[TOOL:x]", ToolError(ErrorType.CONTENT, "fout", False))
    loop = ReactLoop(brain, gw, {"x": DummyTool(err)})

    out = loop.run("hallo")
    assert "inhoudelijke" in out


def test_technical_error_counts_against_limit(tmp_path):
    brain = MagicMock()
    brain.next_step.side_effect = [
        {"type": "tool_call", "tool_name": "x", "parameters": {}},
        {"type": "final", "content": "klaar"},
    ]
    gw = _make_gateway(tmp_path, max_calls=4)
    gw._config.raw["security"]["react_loop"]["max_retries_technical"] = 0
    err = ToolResult(False, None, "[TOOL:x]", ToolError(ErrorType.TECHNICAL, "fout", False))
    loop = ReactLoop(brain, gw, {"x": DummyTool(err)})

    out = loop.run("hallo")
    assert "technische" in out


def test_loop_returns_final_answer_when_no_tool_needed(tmp_path):
    brain = MagicMock()
    brain.next_step.return_value = {"type": "final", "content": "Antwoord"}
    gw = _make_gateway(tmp_path, max_calls=4)
    loop = ReactLoop(brain, gw, {})

    out = loop.run("hallo")
    assert out == "Antwoord"
