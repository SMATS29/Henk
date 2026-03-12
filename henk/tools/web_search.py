"""Web search tool via security proxy."""

from __future__ import annotations

from urllib.parse import quote_plus

from henk.security.proxy import SecurityProxy
from henk.security.source_tag import tag_output
from henk.tools.base import BaseTool, ErrorType, ToolError, ToolResult


class WebSearchTool(BaseTool):
    """Eenvoudige GET-wrapper voor web content."""

    name = "web_search"
    description = "Haal webpagina op via security proxy."
    permissions = ["read"]
    parameters = {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "Zoekterm"}},
        "required": ["query"],
    }

    def __init__(self, proxy: SecurityProxy, timeout_seconds: int = 10):
        self._proxy = proxy
        self._timeout_seconds = timeout_seconds

    def execute(self, **kwargs) -> ToolResult:
        query = kwargs["query"]
        url = f"https://www.google.com/search?q={quote_plus(query)}"
        try:
            response = self._proxy.request("GET", url, timeout=self._timeout_seconds)
            response.raise_for_status()
            text = response.text[:4000]
            tagged = tag_output(self.name, text, external=True)
            return ToolResult(success=True, data=tagged, source_tag="[TOOL:web_search — EXTERNAL]")
        except Exception as error:
            error_type = self.classify_error(error)
            return ToolResult(
                success=False,
                data=None,
                source_tag="[TOOL:web_search — EXTERNAL]",
                error=ToolError(error_type=error_type, message=str(error), retry_useful=True),
            )

    def classify_error(self, error: Exception) -> ErrorType:
        if isinstance(error, PermissionError):
            return ErrorType.CONTENT
        return ErrorType.TECHNICAL
