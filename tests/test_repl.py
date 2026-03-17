import asyncio

import pytest

prompt_toolkit = pytest.importorskip("prompt_toolkit")
Document = prompt_toolkit.document.Document

from copy import deepcopy
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from henk.config import Config, DEFAULT_CONFIG
from henk.gateway import RunStatus, TaskInfo
from henk.repl import (
    SlashCommandAutoSuggest,
    _build_completer,
    _build_bottom_toolbar_markup,
    _build_key_bindings,
    _handle_result_message,
    _message_for_model_error,
    _run_task_with_quality_gate,
    _startup_missing_key_message,
)
from henk.dispatcher import ProgressMessage, ResultMessage
from henk.router import ModelRole, ProviderAttempt, ProviderSelectionError
from henk.router.router import ModelRouter
from henk.router.providers.base import ProviderRequestError


def test_completer_suggests_for_slash_prefix():
    completer = _build_completer()
    completions = list(completer.get_completions(Document(text="/st", cursor_position=3), None))
    texts = [item.text for item in completions]
    assert "/status" in texts
    assert "/stop" in texts


def test_completer_ignores_plain_text():
    completer = _build_completer()
    completions = list(completer.get_completions(Document(text="hallo", cursor_position=5), None))
    assert completions == []


def test_message_for_missing_credentials_error():
    error = ProviderSelectionError(
        ModelRole.DEFAULT,
        [ProviderAttempt("openai/gpt-5.2", "missing_credentials")],
    )

    assert _message_for_model_error(error) == "Ik kan geen model bereiken omdat er geen API key is ingesteld."


def test_message_for_provider_network_error():
    error = ProviderRequestError("openai", "network_unavailable", "connection refused")

    assert _message_for_model_error(error) == "Ik kan het model nu niet bereiken. Check je internet of lokale modelserver."


def test_message_for_unavailable_model_error():
    error = ProviderRequestError("openai", "model_unavailable", "model bestaat niet")

    assert _message_for_model_error(error) == "Ik kan dit model nu niet gebruiken. Check de modelnaam of gebruik een fallbackmodel."


def test_message_for_missing_dependency_error():
    error = ProviderRequestError("openai", "dependency_missing", "package ontbreekt")

    assert _message_for_model_error(error) == "Ik kan het model niet gebruiken omdat de benodigde dependency niet is geinstalleerd."


def test_build_key_bindings_remains_compatible():
    bindings, shift_enter_supported = _build_key_bindings()

    assert bindings is not None
    assert isinstance(shift_enter_supported, bool)


def test_slash_command_auto_suggest_returns_suffix():
    suggestion = SlashCommandAutoSuggest().get_suggestion(None, Document(text="/c", cursor_position=2))

    assert suggestion is not None
    assert suggestion.text == "lear"


def test_slash_command_auto_suggest_ignores_plain_text():
    suggestion = SlashCommandAutoSuggest().get_suggestion(None, Document(text="hallo", cursor_position=5))

    assert suggestion is None


def test_startup_missing_key_message_lists_roles(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    data = deepcopy(DEFAULT_CONFIG)
    data["roles"]["fast"] = {"primary": "openai/gpt-5-mini", "fallback": []}
    data["roles"]["default"] = {"primary": "openai/gpt-5.2", "fallback": []}
    data["roles"]["heavy"] = {"primary": "openai/gpt-5.2", "fallback": []}
    router = ModelRouter(Config(data))

    message = _startup_missing_key_message(router)

    assert message == "Ik heb nog geen API keys beschikbaar voor de volgende modellen: fast, default en heavy."


@patch("henk.repl.run_in_terminal")
def test_handle_result_message_prints_without_waiting_for_enter(mock_run_in_terminal):
    executed = []

    async def _run(func, in_executor=False):
        executed.append("render")
        func()

    mock_run_in_terminal.side_effect = _run
    console = MagicMock()
    gateway = MagicMock()
    task_display = MagicMock()
    session = SimpleNamespace(app=MagicMock())
    active_tasks = {"run-1": object()}

    with patch("henk.output.print_henk") as mock_print_henk:
        asyncio.run(
            _handle_result_message(
                msg=ResultMessage(run_id="run-1", response="klaar", success=True),
                console=console,
                gateway=gateway,
                task_display=task_display,
                session=session,
                active_tasks=active_tasks,
            )
        )

    assert executed == ["render"]
    mock_print_henk.assert_called_once_with(console, "klaar", gateway)
    task_display.print_static_panel.assert_called_once()
    task_display.clear_status.assert_called_once()
    session.app.invalidate.assert_called()
    assert active_tasks == {}


def test_handle_result_message_updates_status_and_invalidates_prompt():
    task_display = MagicMock()
    session = SimpleNamespace(app=MagicMock())

    asyncio.run(
        _handle_result_message(
            msg=ProgressMessage(run_id="run-1", status="Henk denkt..."),
            console=MagicMock(),
            gateway=MagicMock(),
            task_display=task_display,
            session=session,
            active_tasks={},
        )
    )

    task_display.update.assert_called_once_with("Henk denkt...")
    assert session.app.invalidate.call_count >= 1


def test_build_bottom_toolbar_markup_shows_active_task_time_and_tokens():
    now = datetime(2026, 3, 17, 12, 0, 0)
    gateway = MagicMock()
    gateway.get_task_state.return_value = [
        TaskInfo(
            run_id="run-1",
            summary="Essay over Parijs, 500 woorden",
            status=RunStatus.ACTIVE,
            started_at=now - timedelta(minutes=2, seconds=5),
            ended_at=None,
            tokens_input=800,
            tokens_output=450,
        )
    ]
    gateway.session_tokens_total = 1250

    markup = _build_bottom_toolbar_markup(gateway, now=now)

    assert "<b>Essay over Parijs, 500 woorden</b>  2:05  1.2k tokens" in markup
    assert "Sessie: 1.2k tokens" in markup


def test_run_task_with_quality_gate_retries_until_forwarded():
    req = SimpleNamespace(
        task_id="task-1",
        task_description="Schrijf een samenvatting",
        specifications="- kort",
        skill_name=None,
    )
    transcript = MagicMock()
    brain = MagicMock()
    brain.req_final_check = AsyncMock(side_effect=[
        SimpleNamespace(forward_to_user=False, feedback="Voeg een conclusie toe."),
        SimpleNamespace(forward_to_user=True, feedback=""),
    ])
    react_loop = MagicMock()
    react_loop.run = AsyncMock(side_effect=["eerste versie", "tweede versie"])

    response, success, error = asyncio.run(
        _run_task_with_quality_gate(
            brain=brain,
            react_loop=react_loop,
            skill_runner=MagicMock(),
            skill_selector=None,
            req=req,
            on_status=MagicMock(),
            max_content_retries=1,
            transcript=transcript,
        )
    )

    assert success is True
    assert error is None
    assert response == "tweede versie"
    assert react_loop.run.await_count == 2
    assert transcript.log_event.call_count == 2


def test_run_task_with_quality_gate_hides_rejected_result_after_retry_budget():
    req = SimpleNamespace(
        task_id="task-1",
        task_description="Schrijf een samenvatting",
        specifications="",
        skill_name=None,
    )
    transcript = MagicMock()
    brain = MagicMock()
    brain.req_final_check = AsyncMock(return_value=SimpleNamespace(forward_to_user=False, feedback="Nog te vaag."))
    react_loop = MagicMock()
    react_loop.run = AsyncMock(return_value="interne versie")

    response, success, error = asyncio.run(
        _run_task_with_quality_gate(
            brain=brain,
            react_loop=react_loop,
            skill_runner=MagicMock(),
            skill_selector=None,
            req=req,
            on_status=MagicMock(),
            max_content_retries=0,
            transcript=transcript,
        )
    )

    assert success is False
    assert response == ""
    assert "Nog te vaag." in error
