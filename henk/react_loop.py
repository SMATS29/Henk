"""ReAct-loop orkestratie."""

from __future__ import annotations

from typing import Any

from henk.gateway import Gateway, LoopDecision
from henk.tools.base import BaseTool, ToolResult


class ReactLoop:
    """Orkestreert de ReAct-cyclus."""

    def __init__(self, brain: Any, gateway: Gateway, tools: dict[str, BaseTool]):
        self._brain = brain
        self._gateway = gateway
        self._tools = tools

    def run(self, user_message: str) -> str:
        """Voer een volledige ReAct-cyclus uit voor een gebruikersbericht."""
        self._gateway.reset_counters()
        tool_results: list[str] = []

        while True:
            step = self._brain.next_step(user_message=user_message, observations=tool_results)
            if step["type"] == "final":
                return step["content"]

            if step["type"] != "tool_call":
                return "Ik kon de taak niet afronden."

            tool_name = step["tool_name"]
            params = dict(step.get("parameters", {}))

            mapped_tool_name = tool_name
            if tool_name == "file_manager_read":
                mapped_tool_name = "file_manager"
                params = {"action": "read", **params}
            elif tool_name == "file_manager_write":
                mapped_tool_name = "file_manager"
                params = {"action": "write", **params}
            elif tool_name == "file_manager_list":
                mapped_tool_name = "file_manager"
                params = {"action": "list", **params}

            decision = self._gateway.check_tool_call(mapped_tool_name, params)
            if decision.decision == LoopDecision.DENY_KILL_SWITCH:
                return f"Gestopt door kill switch: {decision.reason}."
            if decision.decision == LoopDecision.DENY_LIMIT:
                return "Ik stop hier: tool-limiet bereikt."
            if decision.decision == LoopDecision.DENY_IDENTICAL:
                return "Ik stop hier: identieke tool-call gedetecteerd."

            run_id = self._gateway.log_tool_call(mapped_tool_name, params)
            tool = self._tools[mapped_tool_name]
            if "run_id" in tool.parameters.get("required", []) and "run_id" not in params:
                params["run_id"] = run_id
            result: ToolResult = tool.execute(**params)
            self._gateway.register_tool_result(result)
            self._gateway.log_tool_result(mapped_tool_name, result)
            if result.data:
                tool_results.append(str(result.data))

            if not result.success and result.error:
                if result.error.error_type.value == "content" and self._gateway.content_retry_count > self._gateway.max_retries_content:
                    return "Ik stop: te veel inhoudelijke tool-fouten."
                if result.error.error_type.value == "technical" and self._gateway.technical_retry_count > self._gateway.max_retries_technical:
                    return "Ik stop: te veel technische tool-fouten."
