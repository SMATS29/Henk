"""Tests voor de memory_write tool."""

from henk.memory import MemoryStore, StagingManager
from henk.tools.memory_write import MemoryWriteTool


def test_memory_write_stages_instead_of_writing_active_memory(tmp_path):
    store = MemoryStore(tmp_path)
    staging = StagingManager(tmp_path / ".staged", store)
    tool = MemoryWriteTool(staging)

    result = tool.execute(
        title="Project Henk",
        description="Voortgang",
        content="Nieuwe voortgang",
        reason="Belangrijk voor later",
    )

    assert result.success is True
    assert not (tmp_path / "active" / "project-henk.md").exists()
    pending = list((tmp_path / ".staged" / "pending").glob("*.json"))
    assert len(pending) == 1


def test_memory_write_returns_tagged_tool_result(tmp_path):
    store = MemoryStore(tmp_path)
    staging = StagingManager(tmp_path / ".staged", store)
    tool = MemoryWriteTool(staging)

    result = tool.execute(
        title="Project Henk",
        description="Voortgang",
        content="Nieuwe voortgang",
        reason="Belangrijk voor later",
    )

    assert "[TOOL:memory_write]" in str(result.data)
    assert result.source_tag == "[TOOL:memory_write]"
