"""ReAct-loop orkestratie."""

from __future__ import annotations

from typing import Any, Callable

from henk.gateway import Gateway, LoopDecision
from henk.tools.base import BaseTool, ErrorType, ToolError, ToolResult


class ReactLoop:
    """Orkestreert de ReAct-cyclus."""

    def __init__(self, brain: Any, gateway: Gateway, tools: dict[str, BaseTool]):
        self._brain = brain
        self._gateway = gateway
        self._tools = tools

    def _map_tool(self, tool_name: str, params: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        mapped_params = dict(params)
        if tool_name == "file_manager_read":
            return "file_manager", {"action": "read", **mapped_params}
        if tool_name == "file_manager_write":
            return "file_manager", {"action": "write", **mapped_params}
        if tool_name == "file_manager_list":
            return "file_manager", {"action": "list", **mapped_params}
        return tool_name, mapped_params

    def run(self, user_message: str, on_status: Callable[[str], None] | None = None) -> str:
        """Voer een volledige ReAct-cyclus uit voor een gebruikersbericht."""
        self._gateway.reset_loop_counters()

        def execute_tool(tool_name: str, params: dict[str, Any]) -> ToolResult:
            mapped_name, mapped_params = self._map_tool(tool_name, params)
            if on_status:
                on_status(f"{mapped_name}: {self._tool_detail(mapped_name, mapped_params)}")

            decision = self._gateway.check_tool_call(mapped_name, mapped_params)
            if decision.decision != LoopDecision.ALLOW:
                if decision.decision == LoopDecision.DENY_KILL_SWITCH:
                    reason = f"Gestopt door kill switch: {decision.reason}."
                elif decision.decision == LoopDecision.DENY_LIMIT:
                    reason = "Ik stop hier: tool-limiet bereikt."
                else:
                    reason = "Ik stop hier: identieke tool-call gedetecteerd."
                return ToolResult(
                    success=False,
                    data=None,
                    source_tag="",
                    error=ToolError(ErrorType.CONTENT, reason, retry_useful=False),
                )

            run_id = self._gateway.log_tool_call(mapped_name, mapped_params)
            tool = self._tools.get(mapped_name)
            if not tool:
                return ToolResult(
                    success=False,
                    data=None,
                    source_tag="",
                    error=ToolError(ErrorType.CONTENT, f"Onbekende tool: {mapped_name}", retry_useful=False),
                )

            if mapped_name == "file_manager" and mapped_params.get("action") == "write":
                mapped_params["run_id"] = run_id
            if mapped_name == "code_runner":
                mapped_params["run_id"] = run_id

            result = tool.execute(**mapped_params)
            self._gateway.register_tool_result(result)
            self._gateway.log_tool_result(mapped_name, result)
            if on_status:
                on_status("Henk denkt...")
            return result

        return self._brain.run_with_tools(user_message, execute_tool)

    def _tool_detail(self, tool_name: str, params: dict[str, Any]) -> str:
        if tool_name == "web_search":
            return str(params.get("query", ""))[:50]
        if tool_name == "file_manager":
            action = params.get("action", "")
            path = params.get("path", "")
            return f"{action} {path}"[:50]
        if tool_name == "code_runner":
            return str(params.get("language", "code"))
        if tool_name == "memory_write":
            return str(params.get("title", ""))[:50]
        if tool_name == "reminder":
            return str(params.get("message", ""))[:50]
        return ""
