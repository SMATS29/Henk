"""Tool om geheugenwijzigingen te stagen."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from henk.memory.models import ChangeType, Provenance, StagedChange
from henk.memory.staging import StagingManager
from henk.security.source_tag import tag_output
from henk.tools.base import BaseTool, ErrorType, ToolError, ToolResult


class MemoryWriteTool(BaseTool):
    """Schrijft geheugenwijzigingen altijd naar staging."""

    name = "memory_write"
    description = "Stel een geheugenwijziging voor. Schrijft alleen naar staging."
    permissions = ["write"]
    parameters = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "description": {"type": "string"},
            "content": {"type": "string"},
            "reason": {"type": "string"},
        },
        "required": ["title", "description", "content", "reason"],
    }

    def __init__(self, staging: StagingManager):
        self._staging = staging

    def execute(self, **kwargs) -> ToolResult:
        try:
            title = kwargs["title"].strip()
            description = kwargs["description"].strip()
            content = kwargs["content"].strip()
            reason = kwargs["reason"].strip()
            change = StagedChange(
                id="",
                change_type=ChangeType.CREATE,
                target_item_id=None,
                proposed_content=content,
                proposed_description=description,
                provenance=Provenance.AGENT_SUGGESTED,
                reason=reason,
                timestamp=datetime.now(timezone.utc),
                proposed_title=title,
                target_path=f"active/{self._slugify(title)}.md",
            )
            self._staging.stage_change(change)
            body = f"Geheugenwijziging voor '{title}' staat in staging en wacht op review."
            tagged = tag_output(self.name, body, external=False)
            return ToolResult(success=True, data=tagged, source_tag="[TOOL:memory_write]")
        except Exception as error:
            return ToolResult(
                success=False,
                data=None,
                source_tag="[TOOL:memory_write]",
                error=ToolError(error_type=ErrorType.TECHNICAL, message=str(error), retry_useful=True),
            )

    @staticmethod
    def _slugify(value: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
        return slug or "geheugen"
