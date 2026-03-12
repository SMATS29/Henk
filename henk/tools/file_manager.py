"""Bestandsbeheer met strikte padvalidatie."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from henk.security.path_validator import validate_read_path, validate_write_path
from henk.security.source_tag import tag_output
from henk.tools.base import BaseTool, ErrorType, ToolError, ToolResult


class FileManagerTool(BaseTool):
    """Lees, schrijf en lijst bestanden binnen toegestane scope."""

    name = "file_manager"
    description = "Bestanden lezen en schrijven met deny-by-default rechten."
    permissions = ["read", "write"]
    parameters: dict[str, Any] = {"type": "object", "properties": {}}

    def __init__(self, read_roots: list[str], workspace_dir: Path):
        self._read_roots = read_roots
        self._workspace_dir = workspace_dir

    def read(self, path: str) -> ToolResult:
        try:
            resolved = validate_read_path(path, self._read_roots)
            if not resolved:
                return self._denied("Pad niet toegestaan voor lezen.")
            content = Path(resolved).read_text(encoding="utf-8")
            external = not Path(resolved).is_relative_to(self._workspace_dir.expanduser().resolve())
            tagged = tag_output(self.name, content, external=external)
            return ToolResult(success=True, data=tagged, source_tag=tagged.split("\n", 1)[0])
        except Exception as error:
            return self._error_result(error)

    def write(self, path: str, content: str, run_id: str) -> ToolResult:
        try:
            resolved = validate_write_path(path, run_id, str(self._workspace_dir))
            if not resolved:
                return self._denied("Pad niet toegestaan voor schrijven.")
            target = Path(resolved)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            tagged = tag_output(self.name, f"Geschreven: {target}", external=False)
            return ToolResult(success=True, data=tagged, source_tag="[TOOL:file_manager]")
        except Exception as error:
            return self._error_result(error)

    def list_dir(self, path: str) -> ToolResult:
        try:
            resolved = validate_read_path(path, self._read_roots)
            if not resolved:
                return self._denied("Pad niet toegestaan voor listing.")
            entries = sorted(item.name for item in Path(resolved).iterdir())
            body = "\n".join(entries)
            tagged = tag_output(self.name, body, external=True)
            return ToolResult(success=True, data=tagged, source_tag="[TOOL:file_manager — EXTERNAL]")
        except Exception as error:
            return self._error_result(error)

    def execute(self, **kwargs: Any) -> ToolResult:
        action = kwargs.get("action")
        if action == "read":
            return self.read(kwargs["path"])
        if action == "write":
            return self.write(kwargs["path"], kwargs["content"], kwargs["run_id"])
        if action == "list":
            return self.list_dir(kwargs["path"])
        return self._denied("Onbekende file_manager actie.")

    def classify_error(self, error: Exception) -> ErrorType:
        if isinstance(error, (FileNotFoundError, IsADirectoryError, PermissionError, ValueError)):
            return ErrorType.CONTENT
        return ErrorType.TECHNICAL

    def _denied(self, message: str) -> ToolResult:
        return ToolResult(
            success=False,
            data=None,
            source_tag="[TOOL:file_manager]",
            error=ToolError(error_type=ErrorType.CONTENT, message=message, retry_useful=False),
        )

    def _error_result(self, error: Exception) -> ToolResult:
        error_type = self.classify_error(error)
        return ToolResult(
            success=False,
            data=None,
            source_tag="[TOOL:file_manager]",
            error=ToolError(error_type=error_type, message=str(error), retry_useful=error_type == ErrorType.TECHNICAL),
        )
