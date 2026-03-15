"""Tests voor het taakpaneel en statusbalk."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from henk.gateway import RunStatus, TaskInfo
from henk.task_display import _build_status_bar, _build_task_table, _format_time, _format_tokens


def test_format_time_zero():
    assert _format_time(0) == "0:00"


def test_format_time_seconds():
    assert _format_time(42) == "0:42"


def test_format_time_minutes_and_seconds():
    assert _format_time(62) == "1:02"


def test_format_time_large():
    assert _format_time(3600) == "60:00"


def test_format_tokens_small():
    assert _format_tokens(0) == "0 tokens"
    assert _format_tokens(999) == "999 tokens"


def test_format_tokens_large():
    assert _format_tokens(1500) == "1.5k tokens"
    assert _format_tokens(12345) == "12.3k tokens"


def _make_task(
    run_id="run_1",
    summary="Test taak",
    status=RunStatus.ACTIVE,
    started_at=None,
    ended_at=None,
    tokens_input=0,
    tokens_output=0,
):
    return TaskInfo(
        run_id=run_id,
        summary=summary,
        status=status,
        started_at=started_at or datetime.now(),
        ended_at=ended_at,
        tokens_input=tokens_input,
        tokens_output=tokens_output,
    )


def test_build_task_table_active_before_completed():
    now = datetime.now()
    tasks = [
        _make_task(run_id="r1", summary="Afgerond", status=RunStatus.DONE, started_at=now - timedelta(minutes=5), ended_at=now - timedelta(minutes=3)),
        _make_task(run_id="r2", summary="Actief", status=RunStatus.ACTIVE, started_at=now - timedelta(minutes=1)),
    ]
    table = _build_task_table(tasks)
    # Active task should be first row
    assert table.row_count == 2


def test_build_task_table_max_5_rows():
    tasks = [_make_task(run_id=f"r{i}", summary=f"Taak {i}") for i in range(8)]
    table = _build_task_table(tasks)
    assert table.row_count == 5


def test_build_task_table_truncates_summary():
    long_summary = "A" * 60
    tasks = [_make_task(summary=long_summary)]
    table = _build_task_table(tasks)
    assert table.row_count == 1


def test_build_task_table_empty():
    table = _build_task_table([])
    assert table.row_count == 0


def test_build_status_bar():
    gateway = MagicMock()
    gateway.session_tokens_total = 4821
    gateway.session_tokens_input = 2310
    gateway.session_tokens_output = 2511

    bar = _build_status_bar(gateway)
    text = str(bar)

    assert "4.8k tokens" in text
    assert "2.3k" in text
    assert "2.5k" in text


def test_build_status_bar_zero():
    gateway = MagicMock()
    gateway.session_tokens_total = 0
    gateway.session_tokens_input = 0
    gateway.session_tokens_output = 0

    bar = _build_status_bar(gateway)
    text = str(bar)

    assert "0 tokens" in text
