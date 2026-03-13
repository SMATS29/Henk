import time
from datetime import datetime, timedelta

from henk.heartbeat import Heartbeat, ReminderTool, ScheduledReminder


def test_heartbeat_triggers_callback():
    seen: list[str] = []
    hb = Heartbeat(interval_seconds=0.05)
    hb.start(lambda msg: seen.append(msg))
    hb.add_reminder(ScheduledReminder(id="1", message="ping", trigger_at=datetime.now() + timedelta(milliseconds=10)))
    time.sleep(0.2)
    hb.stop()
    assert "ping" in seen


def test_heartbeat_stop_ends_timer():
    hb = Heartbeat(interval_seconds=1)
    hb.start(lambda _: None)
    hb.stop()
    assert hb.pending_count == 0


def test_reminder_tool_schedules_reminder():
    hb = Heartbeat(interval_seconds=1)
    tool = ReminderTool(hb)
    result = tool.execute(message="test", minutes=1)
    assert result.success is True
    assert hb.pending_count == 1
