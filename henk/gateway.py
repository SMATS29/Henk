"""Gateway: validatie, limieten, logging."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Callable

from henk.brain import Brain
from henk.config import Config
from henk.tools.base import ErrorType, ToolResult
from henk.transcript import TranscriptWriter


class KillSwitchActive(Exception):
    """Raised wanneer een kill switch actief is."""

    def __init__(self, switch_type: str):
        self.switch_type = switch_type
        super().__init__(f"Kill switch actief: {switch_type}")


class LoopDecision(str, Enum):
    """Uitkomst van tool-call validatie."""

    ALLOW = "allow"
    DENY_LIMIT = "deny_limit"
    DENY_IDENTICAL = "deny_identical"
    DENY_KILL_SWITCH = "deny_kill_switch"


@dataclass
class ToolCallDecision:
    """Resultaat voor tool-call check."""

    decision: LoopDecision
    reason: str


class Gateway:
    """Bewaakt limieten, valideert berichten, logt alles."""

    def __init__(self, config: Config, brain: Brain, transcript: TranscriptWriter):
        self._config = config
        self._brain = brain
        self._transcript = transcript
        self._tool_call_count = 0
        self._content_retry_count = 0
        self._technical_retry_count = 0
        self._call_history: set[str] = set()
        self._current_run_id: str | None = None
        self._react_loop = None

    @property
    def tool_call_count(self) -> int:
        return self._tool_call_count

    @property
    def current_run_id(self) -> str | None:
        return self._current_run_id

    @property
    def content_retry_count(self) -> int:
        return self._content_retry_count

    @property
    def technical_retry_count(self) -> int:
        return self._technical_retry_count

    @property
    def max_retries_content(self) -> int:
        return self._config.max_retries_content

    @property
    def max_retries_technical(self) -> int:
        return self._config.max_retries_technical

    def reset_counters(self) -> None:
        """Reset tellers voor een nieuwe taak."""
        self._tool_call_count = 0
        self._content_retry_count = 0
        self._technical_retry_count = 0
        self._call_history = set()
        self._current_run_id = None

    def check_kill_switches(self) -> str | None:
        """Check kill switches. Geeft het type terug als actief, anders None."""
        control_dir = self._config.control_dir

        hard_stop = control_dir / "hard_stop"
        if hard_stop.exists() and hard_stop.read_text(encoding="utf-8").strip().lower() == "true":
            return "hard_stop"

        graceful_stop = control_dir / "graceful_stop"
        if graceful_stop.exists() and graceful_stop.read_text(encoding="utf-8").strip().lower() == "true":
            return "graceful_stop"

        return None

    def _make_call_hash(self, tool_name: str, params: dict) -> str:
        payload = json.dumps({"tool": tool_name, "params": params}, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _ensure_run_id(self) -> str:
        if self._current_run_id is None:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            short = uuid.uuid4().hex[:4]
            run_id = f"run_{stamp}_{short}"
            run_root = self._config.workspace_dir / run_id
            (run_root / "scratch").mkdir(parents=True, exist_ok=True)
            (run_root / "output").mkdir(parents=True, exist_ok=True)
            self._current_run_id = run_id
        return self._current_run_id

    def check_tool_call(self, tool_name: str, params: dict) -> ToolCallDecision:
        """Check of een tool-call is toegestaan."""
        active_switch = self.check_kill_switches()
        if active_switch:
            return ToolCallDecision(LoopDecision.DENY_KILL_SWITCH, active_switch)

        if self._tool_call_count >= self._config.max_tool_calls:
            return ToolCallDecision(LoopDecision.DENY_LIMIT, "max_tool_calls")

        call_hash = self._make_call_hash(tool_name, params)
        if call_hash in self._call_history:
            return ToolCallDecision(LoopDecision.DENY_IDENTICAL, "identieke tool-call")

        self._call_history.add(call_hash)
        self._tool_call_count += 1
        return ToolCallDecision(LoopDecision.ALLOW, "ok")

    def register_tool_result(self, result: ToolResult) -> None:
        """Registreer het resultaat en update retry-tellers."""
        if result.success or not result.error:
            return
        if result.error.error_type == ErrorType.CONTENT:
            self._content_retry_count += 1
        elif result.error.error_type == ErrorType.TECHNICAL:
            self._technical_retry_count += 1

    def set_react_loop(self, react_loop) -> None:
        """Koppel de ReAct-loop aan de Gateway."""
        self._react_loop = react_loop

    def process(self, user_message: str, on_status: Callable[[str], None] | None = None) -> str:
        """Verwerk een gebruikersbericht via de ReAct-loop."""
        active_switch = self.check_kill_switches()
        if active_switch:
            raise KillSwitchActive(active_switch)

        if not user_message or not user_message.strip():
            return ""

        self.reset_counters()
        self._transcript.write("user", user_message)
        if self._react_loop is None:
            response = self._brain.think(user_message)
        else:
            response = self._react_loop.run(user_message, on_status=on_status)
        self._transcript.write("assistant", response)
        return response

    def get_greeting(self) -> str:
        """Bouw een lokale startup-begroeting zonder modelcall."""
        user_name = self._config.user_name
        greeting = f"Hoi, {user_name}. Zeg het maar." if user_name else "Hoi. Zeg het maar."
        self._transcript.write("assistant", greeting)
        return greeting

    def log_tool_call(self, tool_name: str, params: dict) -> str:
        """Log een tool-call event en return run_id."""
        run_id = self._ensure_run_id()
        self._transcript.log_event(
            {
                "type": "tool_call",
                "session_id": self._transcript.session_id,
                "run_id": run_id,
                "tool": tool_name,
                "params": params,
                "loop_count": self._tool_call_count,
            }
        )
        return run_id

    def log_tool_result(self, tool_name: str, result: ToolResult) -> None:
        """Log een tool-result event."""
        payload = "[MEMORY — niet gelogd]" if tool_name == "memory_write" else result.data
        self._transcript.log_event(
            {
                "type": "tool_result",
                "session_id": self._transcript.session_id,
                "run_id": self._current_run_id,
                "tool": tool_name,
                "success": result.success,
                "source_tag": result.source_tag,
                "payload": payload,
                "error": result.error.message if result.error else None,
            }
        )


    def log_skill_event(self, event_type: str, skill_name: str, step_number: int, detail: str = "") -> None:
        """Log een skill-gerelateerd event."""
        self._transcript.log_event(
            {
                "type": f"skill.{event_type}",
                "session_id": self._transcript.session_id,
                "skill": skill_name,
                "step": step_number,
                "detail": detail,
            }
        )
