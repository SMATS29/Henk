from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from henk.security.source_tag import tag_output
from henk.tools.base import BaseTool, ToolResult


@dataclass
class ScheduledReminder:
    id: str
    message: str
    trigger_at: datetime
    triggered: bool = False


class Heartbeat:
    """Simpele timer voor geplande meldingen tijdens chat."""

    def __init__(self, interval_seconds: int = 30):
        self._interval = interval_seconds
        self._reminders: list[ScheduledReminder] = []
        self._timer: threading.Timer | None = None
        self._running = False
        self._callback: Callable[[str], None] | None = None

    def start(self, callback: Callable[[str], None]) -> None:
        self._callback = callback
        self._running = True
        self._tick()

    def stop(self) -> None:
        self._running = False
        if self._timer:
            self._timer.cancel()

    def add_reminder(self, reminder: ScheduledReminder) -> None:
        self._reminders.append(reminder)

    def _tick(self) -> None:
        if not self._running:
            return

        now = datetime.now()
        for reminder in self._reminders:
            if not reminder.triggered and reminder.trigger_at <= now:
                reminder.triggered = True
                if self._callback:
                    self._callback(reminder.message)

        self._reminders = [r for r in self._reminders if not r.triggered]
        self._timer = threading.Timer(self._interval, self._tick)
        self._timer.daemon = True
        self._timer.start()

    @property
    def pending_count(self) -> int:
        return len([r for r in self._reminders if not r.triggered])


class ReminderTool(BaseTool):
    name = "reminder"
    description = "Plan een herinnering. Werkt alleen tijdens de huidige chat-sessie."
    permissions = ["write"]
    parameters = {
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "De herinnering"},
            "minutes": {"type": "integer", "description": "Over hoeveel minuten"},
        },
        "required": ["message", "minutes"],
    }

    def __init__(self, heartbeat: Heartbeat):
        self._heartbeat = heartbeat

    def execute(self, **kwargs) -> ToolResult:
        reminder = ScheduledReminder(
            id=uuid.uuid4().hex[:8],
            message=str(kwargs["message"]),
            trigger_at=datetime.now() + timedelta(minutes=int(kwargs["minutes"])),
        )
        self._heartbeat.add_reminder(reminder)
        tagged = tag_output(self.name, f"Herinnering gepland over {kwargs['minutes']} minuten.", external=False)
        return ToolResult(success=True, data=tagged, source_tag=tagged)
