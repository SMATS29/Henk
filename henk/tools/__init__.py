"""Tools package voor Henk v0.2."""

from henk.tools.base import BaseTool, ErrorType, ToolError, ToolResult
from henk.tools.code_runner import CodeRunnerTool
from henk.tools.file_manager import FileManagerTool
from henk.tools.web_search import WebSearchTool

__all__ = [
    "BaseTool",
    "ErrorType",
    "ToolError",
    "ToolResult",
    "CodeRunnerTool",
    "FileManagerTool",
    "WebSearchTool",
]
