"""Code uitvoeren via subprocess met beperkingen."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from henk.security.source_tag import tag_output
from henk.tools.base import BaseTool, ErrorType, ToolError, ToolResult


class CodeRunnerTool(BaseTool):
    """Voert python/bash uit in workspace scratch map.

    Bekende beperking: dit gebruikt subprocess en geen echte container-isolatie.
    """

    name = "code_runner"
    description = "Voer Python of bash code uit in beperkte omgeving."
    permissions = ["write", "execute"]
    parameters = {
        "type": "object",
        "properties": {
            "language": {"type": "string", "enum": ["python", "bash"]},
            "code": {"type": "string"},
            "run_id": {"type": "string"},
        },
        "required": ["language", "code", "run_id"],
    }

    def __init__(self, workspace_dir: Path, max_runtime_seconds: int = 60):
        self._workspace_dir = workspace_dir
        self._max_runtime_seconds = max_runtime_seconds

    def execute(self, **kwargs) -> ToolResult:
        language = kwargs["language"]
        code = kwargs["code"]
        run_id = kwargs["run_id"]

        run_root = self._workspace_dir / run_id
        scratch = run_root / "scratch"
        output = run_root / "output"
        scratch.mkdir(parents=True, exist_ok=True)
        output.mkdir(parents=True, exist_ok=True)

        script_name = "script.py" if language == "python" else "script.sh"
        script_path = scratch / script_name
        script_path.write_text(code, encoding="utf-8")

        cmd = ["python", str(script_path)] if language == "python" else ["bash", str(script_path)]
        try:
            result = subprocess.run(
                cmd,
                cwd=scratch,
                capture_output=True,
                text=True,
                timeout=self._max_runtime_seconds,
                env={"PATH": os.environ.get("PATH", "")},
            )
            combined = (result.stdout or "") + (result.stderr or "")
            (output / "result.txt").write_text(combined, encoding="utf-8")
            tagged = tag_output(self.name, combined.strip() or "(geen output)", external=False)
            return ToolResult(success=result.returncode == 0, data=tagged, source_tag="[TOOL:code_runner]")
        except subprocess.TimeoutExpired as error:
            return ToolResult(
                success=False,
                data=None,
                source_tag="[TOOL:code_runner]",
                error=ToolError(error_type=ErrorType.TECHNICAL, message=f"Timeout: {error}", retry_useful=False),
            )
