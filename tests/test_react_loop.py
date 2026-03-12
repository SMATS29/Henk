"""Tests voor ReAct-loop gedrag."""

from unittest.mock import MagicMock

from henk.config import Config, DEFAULT_CONFIG
from henk.gateway import Gateway
from henk.react_loop import ReactLoop
from henk.tools.base import ErrorType, ToolError, ToolResult


class DummyTool:
    def __init__(self, result: ToolResult):
        self._result = result

    def execute(self, **kwargs):
        return self._result


def _make_gateway(tmp_path, max_calls=4):
    data = DEFAULT_CONFIG.copy()
    data["paths"] = {
        "data_dir": str(tmp_path),
        "memory_dir": str(tmp_path / "memory"),
        "workspace_dir": str(tmp_path / "workspace"),
        "logs_dir": str(tmp_path / "logs"),
        "control_dir": str(tmp_path / "control"),
    }
    data["security"]["react_loop"]["max_tool_calls"] = max_calls
    cfg = Config(data)
    cfg.control_dir.mkdir(parents=True, exist_ok=True)
    (cfg.control_dir / "hard_stop").write_text("false", encoding="utf-8")
    (cfg.control_dir / "graceful_stop").write_text("false", encoding="utf-8")
    from henk.transcript import TranscriptWriter

    return Gateway(cfg, MagicMock(), TranscriptWriter(cfg.logs_dir))


def test_loop_runs_brain_with_tool_executor(tmp_path):
    gw = _make_gateway(tmp_path)
    tool = DummyTool(ToolResult(True, "ok", "[TOOL:x]"))
    brain = MagicMock()

    def run_with_tools(user_message, executor):
        result = executor("x", {})
        assert result.success is True
        return "Antwoord"

    brain.run_with_tools.side_effect = run_with_tools
    loop = ReactLoop(brain, gw, {"x": tool})
    out = loop.run("hallo")
    assert out == "Antwoord"


def test_map_file_manager_tools(tmp_path):
    gw = _make_gateway(tmp_path)
    brain = MagicMock()
    brain.run_with_tools.side_effect = lambda message, exec_tool: exec_tool("file_manager_read", {"path": "a"}).data
    tool = DummyTool(ToolResult(True, "gelezen", ""))
    loop = ReactLoop(brain, gw, {"file_manager": tool})

    out = loop.run("hallo")
    assert out == "gelezen"


def test_unknown_tool_returns_error(tmp_path):
    gw = _make_gateway(tmp_path)
    brain = MagicMock()

    def run_with_tools(user_message, executor):
        result = executor("onbekend", {})
        return result.error.message

    brain.run_with_tools.side_effect = run_with_tools
    loop = ReactLoop(brain, gw, {})
    out = loop.run("hallo")
    assert "Onbekende tool" in out


def test_denied_limit_returns_error_result(tmp_path):
    gw = _make_gateway(tmp_path, max_calls=0)
    brain = MagicMock()

    def run_with_tools(user_message, executor):
        result = executor("x", {})
        return result.error.message

    brain.run_with_tools.side_effect = run_with_tools
    loop = ReactLoop(brain, gw, {"x": DummyTool(ToolResult(True, "ok", ""))})
    out = loop.run("hallo")
    assert "tool-limiet" in out


def test_denied_identical_returns_error_result(tmp_path):
    gw = _make_gateway(tmp_path, max_calls=4)
    brain = MagicMock()

    def run_with_tools(user_message, executor):
        executor("x", {})
        result = executor("x", {})
        return result.error.message

    brain.run_with_tools.side_effect = run_with_tools
    loop = ReactLoop(brain, gw, {"x": DummyTool(ToolResult(True, "ok", ""))})
    out = loop.run("hallo")
    assert "identieke" in out


def test_registers_tool_errors(tmp_path):
    gw = _make_gateway(tmp_path)
    brain = MagicMock()
    err = ToolResult(False, None, "", ToolError(ErrorType.TECHNICAL, "fout", False))

    def run_with_tools(user_message, executor):
        result = executor("x", {})
        assert result.error.error_type == ErrorType.TECHNICAL
        return "klaar"

    brain.run_with_tools.side_effect = run_with_tools
    loop = ReactLoop(brain, gw, {"x": DummyTool(err)})
    out = loop.run("hallo")
    assert out == "klaar"
    assert gw.technical_retry_count == 1
