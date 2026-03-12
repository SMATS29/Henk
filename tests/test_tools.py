"""Tests voor tools."""

import time
from unittest.mock import MagicMock

from henk.security.proxy import SecurityProxy
from henk.tools.code_runner import CodeRunnerTool
from henk.tools.file_manager import FileManagerTool
from henk.tools.web_search import WebSearchTool


def test_web_search_uses_security_proxy():
    proxy = MagicMock(spec=SecurityProxy)
    response = MagicMock()
    response.text = "abc"
    response.raise_for_status.return_value = None
    proxy.request.return_value = response

    tool = WebSearchTool(proxy=proxy, timeout_seconds=1)
    result = tool.execute(query="henk")

    assert result.success is True
    proxy.request.assert_called_once()


def test_file_manager_refuses_read_outside_roots(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    tool = FileManagerTool([str(tmp_path / "allowed")], ws)

    result = tool.read(str(tmp_path / "blocked.txt"))
    assert result.success is False


def test_file_manager_refuses_write_outside_workspace(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    tool = FileManagerTool([str(tmp_path)], ws)

    result = tool.write(str(tmp_path / "evil.txt"), "x", "run_1")
    assert result.success is False


def test_file_manager_resolves_symlinks(tmp_path):
    ws = tmp_path / "ws"
    read = tmp_path / "read"
    outside = tmp_path / "outside"
    ws.mkdir()
    read.mkdir()
    outside.mkdir()
    (outside / "s.txt").write_text("secret", encoding="utf-8")
    (read / "link.txt").symlink_to(outside / "s.txt")

    tool = FileManagerTool([str(read)], ws)
    result = tool.read(str(read / "link.txt"))
    assert result.success is False


def test_code_runner_respects_timeout(tmp_path):
    tool = CodeRunnerTool(tmp_path, max_runtime_seconds=1)
    start = time.time()
    result = tool.execute(language="python", code="import time\ntime.sleep(2)", run_id="run_1")
    elapsed = time.time() - start

    assert result.success is False
    assert elapsed < 2


def test_tools_return_tagged_tool_result(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    tool = FileManagerTool([str(ws)], ws)
    res = tool.write("x.txt", "hallo", "run_1")
    assert "[TOOL:file_manager]" in str(res.data)
