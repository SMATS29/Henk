"""Interactieve REPL met prompt_toolkit autocomplete."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from html import escape

from prompt_toolkit import PromptSession
from prompt_toolkit.application import run_in_terminal
from prompt_toolkit.auto_suggest import AutoSuggest, Suggestion
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style
from rich.console import Console

PROMPT_STYLE = Style.from_dict({"prompt": "bold cyan"})


def _message_for_model_error(error: Exception) -> str:
    from henk.router import ProviderSelectionError
    from henk.router.providers.base import ProviderRequestError

    if isinstance(error, ProviderSelectionError):
        reasons = error.reasons
        if reasons == {"missing_credentials"}:
            return "Ik kan geen model bereiken omdat er geen API key is ingesteld."
        if reasons <= {"provider_unavailable"}:
            return "Ik kan het model nu niet bereiken. Check je internet of lokale modelserver."
        if "missing_credentials" in reasons and "provider_unavailable" in reasons:
            return "Ik kan geen model bereiken: er ontbreekt een API key en er is geen werkende fallbackprovider."
        if reasons == {"unsupported_tools"}:
            return "Ik kan deze taak nu niet uitvoeren met de beschikbare modellen."
        return "Ik kan even geen model kiezen. Check je configuratie en verbinding."
    if isinstance(error, ProviderRequestError):
        if error.reason == "model_unavailable":
            return "Ik kan dit model nu niet gebruiken. Check de modelnaam of gebruik een fallbackmodel."
        if error.reason == "network_unavailable":
            return "Ik kan het model nu niet bereiken. Check je internet of lokale modelserver."
        if error.reason == "authentication_failed":
            return "Ik kan het model niet gebruiken. Check je API key."
        if error.reason == "missing_credentials":
            return "Ik kan geen model bereiken omdat er geen API key is ingesteld."
        if error.reason == "dependency_missing":
            return "Ik kan het model niet gebruiken omdat de benodigde dependency niet is geinstalleerd."
        return "De modelaanroep mislukte. Probeer het zo nog eens."
    return "Ik kan even niet bij mijn brein. Check je API key of internetverbinding."


def _format_natural_list(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} en {items[1]}"
    return f"{', '.join(items[:-1])} en {items[-1]}"


def _startup_missing_key_message(router: ModelRouter) -> str | None:
    from henk.router import ModelRole, ProviderSelectionError

    missing_roles: list[str] = []
    for role in ModelRole:
        try:
            router.get_provider(role)
        except ProviderSelectionError as error:
            if error.reasons == {"missing_credentials"}:
                missing_roles.append(role.value)

    if not missing_roles:
        return None

    return (
        "Ik heb nog geen API keys beschikbaar voor de volgende modellen: "
        f"{_format_natural_list(missing_roles)}."
    )


class SlashCommandAutoSuggest(AutoSuggest):
    def get_suggestion(self, buffer, document):
        text = document.text_before_cursor.strip()
        if not text.startswith("/") or " " in text:
            return None

        from henk.commands import get_command_names

        matches = sorted(
            (command for command in get_command_names() if command.startswith(text) and command != text),
            key=lambda command: (len(command), command),
        )
        if not matches:
            return None

        return Suggestion(matches[0][len(text):])


def _build_completer() -> WordCompleter:
    from henk.commands import get_command_names

    return WordCompleter(
        get_command_names(),
        sentence=True,
        meta_dict={
            "/stop": "Hard stop — alles stopt direct",
            "/pause": "Pauzeer — geen nieuwe taken",
            "/resume": "Hervat na pause of stop",
            "/model": "Beheer taaktypes, modellen en API keys",
            "/status": "Toon status van Henk",
            "/review": "Dagelijkse memory review",
            "/config": "Bekijk configuratie",
            "/help": "Toon beschikbare commands",
            "/exit": "Sluit Henk af",
            "/clear": "Wis het scherm",
            "/history": "Toon gespreksgeschiedenis",
        },
    )


def _build_memory_services(config: Config):
    from henk.memory import MemoryRetrieval, MemoryStore, RelevanceScorer, StagingManager

    store = MemoryStore(config.memory_dir, initial_score=config.memory_scoring["initial_score"])
    staging = StagingManager(config.memory_dir / ".staged", store)
    scorer = RelevanceScorer(**config.memory_scoring)
    retrieval = MemoryRetrieval(
        config.memory_dir,
        store,
        scorer,
        vector_enabled=config.memory_vector_enabled,
        relevance_threshold=config.memory_relevance_threshold,
    )
    return store, staging, scorer, retrieval


def _build_key_bindings() -> tuple[KeyBindings, bool]:
    bindings = KeyBindings()
    shift_enter_supported = False

    @bindings.add("enter")
    def handle_enter(event) -> None:
        event.current_buffer.validate_and_handle()

    try:
        @bindings.add("s-enter")
        def handle_shift_enter(event) -> None:
            event.current_buffer.insert_text("\n")

        shift_enter_supported = True
    except ValueError:
        shift_enter_supported = False

    @bindings.add("tab")
    def handle_tab(event) -> None:
        suggestion = event.current_buffer.suggestion
        if suggestion:
            event.current_buffer.insert_text(suggestion.text)
            return
        event.current_buffer.start_completion(select_first=False)

    return bindings, shift_enter_supported


async def _conversation_loop(
    brain,
    gateway,
    task_queue: asyncio.Queue,
    config,
    console: Console,
    session,
    task_display,
    skill_selector,
    staging,
    command_context: dict,
    active_tasks: dict[str, object],
) -> None:
    from henk.commands import dispatch_command
    from henk.dispatcher import CancelMessage, ProgressMessage, ResultMessage, TaskMessage
    from henk.gateway import KillSwitchActive
    from henk.memory import ChangeType, Provenance, StagedChange
    from henk.output import print_henk
    from henk.requirements import Requirements, RequirementsStatus
    from henk.router import ProviderSelectionError
    from henk.router.providers.base import ProviderRequestError

    while True:
        # Wacht op gebruikersinput
        try:
            user_input = await session.prompt_async(
                HTML("<prompt>❯ </prompt>"),
                completer=_build_completer(),
            )
        except EOFError:
            break
        except KeyboardInterrupt:
            continue

        stripped = user_input.strip()
        if not stripped:
            continue

        if stripped.startswith("/"):
            result = dispatch_command(stripped, config, console, **command_context)
            if result == "exit":
                break
            continue

        try:
            # Bouw lijst van actieve taken voor routing
            active_task_summaries = [
                (req.task_id, req.summary or req.task_description)
                for req in active_tasks.values()
            ]

            route = await brain.classify_and_build(stripped, active_task_summaries)
            route_type = route.get("type", "nieuwe_taak")
            route_task_id = route.get("task_id")

            if route_type == "gesprek":
                response = await brain.think(stripped)
                if response:
                    print_henk(console, response, gateway)

            elif route_type == "update_taak" and route_task_id and route_task_id in active_tasks:
                req = active_tasks[route_task_id]
                async with req.update_lock:
                    await brain.req_merge(req, stripped)
                console.print("[dim]Wordt meegenomen.[/dim]")

            else:
                # nieuwe_taak
                req = Requirements(
                    task_description=str(route.get("task_description") or stripped).strip() or stripped,
                    specifications=str(route.get("specifications") or ""),
                    status=RequirementsStatus.DRAFT,
                )
                req.summary = str(route.get("summary") or req.task_description[:60]).strip() or req.task_description[:60]

                if skill_selector:
                    skill = skill_selector.select(req.task_description)
                    if skill:
                        req.skill_name = skill.name

                question = route.get("question")
                if question:
                    print_henk(console, question, gateway)
                    try:
                        follow_up = await session.prompt_async(
                            HTML("<prompt>❯ </prompt>"),
                            completer=_build_completer(),
                        )
                    except (EOFError, KeyboardInterrupt):
                        console.print("[dim]Taak niet gestart.[/dim]")
                        continue
                    follow_up = follow_up.strip()
                    if not follow_up:
                        console.print("[dim]Taak niet gestart.[/dim]")
                        continue
                    await brain.req_merge(req, follow_up)
                    req.pending_update = False  # reset, was net gebouwd

                req.confirm()

                run_id = req.task_id
                active_tasks[run_id] = req

                await task_queue.put(TaskMessage(run_id=run_id, requirements=req))
                summary = req.summary or req.task_description[:50]
                console.print(f"[dim]Taak gestart: {summary}. Je kunt intussen gewoon doorpraten.[/dim]")

        except KillSwitchActive as error:
            console.print(f"[red]Henk is gestopt ({error.switch_type}). Typ /resume om te hervatten.[/red]")
        except (ProviderSelectionError, ProviderRequestError) as error:
            console.print(f"[red]{_message_for_model_error(error)}[/red]\n")
        except Exception:
            console.print("[red]Ik kan even niet bij mijn brein. Check je API key of internetverbinding.[/red]\n")

    # Sessie-samenvatting bij afsluiten
    if brain.has_history:
        summary = await brain.summarize_session()
        if summary:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            staging.stage_change(
                StagedChange(
                    id="",
                    change_type=ChangeType.CREATE,
                    target_item_id=None,
                    proposed_content=summary,
                    proposed_description="Korte samenvatting van een recente chatsessie.",
                    provenance=Provenance.AGENT_SUGGESTED,
                    reason="Automatische sessiesamenvatting bij afsluiten van henk.",
                    timestamp=datetime.now(timezone.utc),
                    proposed_title=f"Sessie {today}",
                    target_path=f"episodes/{today}.md",
                )
            )
            console.print("[dim]Sessie-samenvatting in staging gezet.[/dim]")


def _build_task_message(requirements) -> str:
    task_msg = requirements.task_description
    specifications = requirements.specifications
    if isinstance(specifications, list):
        specifications = "\n".join(f"- {str(item).strip()}" for item in specifications if str(item).strip())
    if specifications:
        task_msg += "\n\nEisen:\n" + str(specifications)
    return task_msg


def _build_retry_task_message(requirements, previous_result: str, feedback: str) -> str:
    base = _build_task_message(requirements)
    return (
        f"{base}\n\n"
        "Vorige poging:\n"
        f"{previous_result}\n\n"
        "Interne kwaliteitscontrole:\n"
        f"{feedback or 'Verbeter het resultaat zodat het volledig aan de taak en eisen voldoet.'}\n\n"
        "Maak een verbeterde versie. Geef alleen het nieuwe eindresultaat terug."
    )


def _build_bottom_toolbar_markup(gateway, now: datetime | None = None) -> str:
    parts: list[str] = []
    current_time = now or datetime.now()

    for task in gateway.get_task_state():
        if task.status.value != "active":
            continue
        elapsed = max((current_time - task.started_at).total_seconds(), 0)
        minutes = int(elapsed) // 60
        secs = int(elapsed) % 60
        total_tokens = task.tokens_input + task.tokens_output
        tok_str = f"{total_tokens}" if total_tokens < 1000 else f"{total_tokens / 1000:.1f}k"
        summary = escape((task.summary or "taak")[:35])
        parts.append(f"<b>{summary}</b>  {minutes}:{secs:02d}  {tok_str} tokens")

    total = gateway.session_tokens_total
    total_str = f"{total} tokens" if total < 1000 else f"{total / 1000:.1f}k tokens"
    parts.append(f"Sessie: {total_str}")
    return "  ·  ".join(parts)


async def _run_task_with_quality_gate(
    *,
    brain,
    react_loop,
    skill_runner,
    skill_selector,
    req,
    on_status,
    max_content_retries: int,
    transcript,
) -> tuple[str, bool, str | None]:
    from henk.brain import FinalCheckDecision

    skill = skill_selector.select(req.task_description) if req.skill_name and skill_selector else None
    task_msg = _build_task_message(req)
    attempt = 0
    max_attempts = max(1, max_content_retries + 1)

    while attempt < max_attempts:
        use_skill = attempt == 0 and skill is not None
        if use_skill:
            response = await skill_runner.run(skill, req, on_status=on_status)
        else:
            response = await react_loop.run(
                task_msg,
                on_status=on_status,
                requirements=req,
            )

        decision = await brain.req_final_check(req, response)
        transcript.log_event(
            {
                "type": "task.final_check",
                "task_id": req.task_id,
                "attempt": attempt + 1,
                "forward_to_user": decision.forward_to_user,
                "feedback": decision.feedback,
            }
        )
        if decision.forward_to_user:
            return response, True, None

        attempt += 1
        if attempt >= max_attempts:
            feedback = decision.feedback.strip()
            error_msg = "Ik heb wel aan de taak gewerkt, maar het resultaat voldoet nog niet genoeg om door te sturen."
            if feedback:
                error_msg = f"{error_msg} {feedback}"
            return "", False, error_msg

        if on_status:
            on_status("Henk verbetert het resultaat...")
        task_msg = _build_retry_task_message(req, response, decision.feedback)

    return "", False, "Ik kon geen bruikbaar resultaat afronden."


async def _render_while_prompt_active(session, render_fn) -> None:
    await run_in_terminal(render_fn, in_executor=False)
    if getattr(session, "app", None) is not None:
        session.app.invalidate()


async def _handle_result_message(
    *,
    msg,
    console: Console,
    gateway,
    task_display,
    session,
    active_tasks: dict[str, object],
    notified_runs: set | None = None,
) -> None:
    from henk.dispatcher import ProgressMessage, ResultMessage
    from henk.output import print_henk

    if notified_runs is None:
        notified_runs = set()

    if isinstance(msg, ProgressMessage):
        task_display.update(msg.status)
        if msg.run_id not in notified_runs:
            notified_runs.add(msg.run_id)
            status_text = msg.status

            def _print_status() -> None:
                console.print(f"[dim cyan]⟳ {status_text}[/dim cyan]")

            await _render_while_prompt_active(session, _print_status)
        if getattr(session, "app", None) is not None:
            session.app.invalidate()
        return

    if not isinstance(msg, ResultMessage):
        return

    def _render_result() -> None:
        if msg.success:
            print_henk(console, msg.response, gateway)
        else:
            console.print(f"[red]{msg.error}[/red]")
            console.print()
        task_display.print_static_panel()

    await _render_while_prompt_active(session, _render_result)
    task_display.clear_status()
    if getattr(session, "app", None) is not None:
        session.app.invalidate()
    active_tasks.pop(msg.run_id, None)


async def _result_loop(
    *,
    result_queue: asyncio.Queue,
    console: Console,
    gateway,
    task_display,
    session,
    active_tasks: dict[str, object],
) -> None:
    notified_runs: set = set()
    while True:
        msg = await result_queue.get()
        try:
            await _handle_result_message(
                msg=msg,
                console=console,
                gateway=gateway,
                task_display=task_display,
                session=session,
                active_tasks=active_tasks,
                notified_runs=notified_runs,
            )
        finally:
            result_queue.task_done()


async def _work_loop(
    brain,
    gateway,
    react_loop,
    skill_runner,
    skill_selector,
    config,
    task_queue: asyncio.Queue,
    result_queue: asyncio.Queue,
    task_display,
    transcript,
) -> None:
    from henk.dispatcher import CancelMessage, ProgressMessage, ResultMessage, TaskMessage
    from henk.gateway import KillSwitchActive

    while True:
        message = await task_queue.get()

        if isinstance(message, CancelMessage):
            gateway.cancel_run(message.run_id)
            task_queue.task_done()
            continue

        if not isinstance(message, TaskMessage):
            task_queue.task_done()
            continue

        req = message.requirements
        run_id = message.run_id  # task_id, used for queue tracking

        # Start de run
        gw_run_id = gateway.start_run(req.summary or req.task_description[:80])
        gateway.active_requirements[req.task_id] = req

        await result_queue.put(ProgressMessage(run_id=run_id, status=req.summary or req.task_description[:50]))

        req.start_execution()
        transcript.write("user", req.task_description)

        response = ""
        success = True
        error_msg = None

        def _on_status(s: str) -> None:
            try:
                result_queue.put_nowait(ProgressMessage(run_id=run_id, status=s))
            except asyncio.QueueFull:
                pass

        try:
            response, success, error_msg = await _run_task_with_quality_gate(
                brain=brain,
                react_loop=react_loop,
                skill_runner=skill_runner,
                skill_selector=skill_selector,
                req=req,
                on_status=_on_status,
                max_content_retries=config.max_retries_content,
                transcript=transcript,
            )

            if success:
                req.complete(response)
                gateway.complete_run(gw_run_id)
                transcript.write("assistant", response)
            else:
                gateway.fail_run(gw_run_id)
                req.fail(error_msg or "Resultaat afgekeurd door kwaliteitscontrole.")
                transcript.write("assistant", error_msg or "Resultaat afgekeurd door kwaliteitscontrole.")

        except KillSwitchActive as e:
            gateway.fail_run(gw_run_id)
            req.fail(str(e))
            success = False
            error_msg = f"Henk is gestopt ({e.switch_type}). Typ /resume om te hervatten."
        except Exception as e:
            gateway.fail_run(gw_run_id)
            req.fail(str(e))
            success = False
            error_msg = "Ik kan even niet bij mijn brein. Check je API key of internetverbinding."
        finally:
            gateway.active_requirements.pop(req.task_id, None)

        await result_queue.put(ResultMessage(
            run_id=run_id,
            response=response,
            success=success,
            error=error_msg,
        ))
        task_queue.task_done()


async def start_repl(config: Config, console: Console) -> None:
    from henk.brain import Brain
    from henk.commands import dispatch_command
    from henk.gateway import Gateway, KillSwitchActive
    from henk.heartbeat import Heartbeat, ReminderTool
    from henk.model_gateway import ModelGateway
    from henk.output import print_henk
    from henk.react_loop import ReactLoop
    from henk.router import ModelRouter, ProviderSelectionError
    from henk.router.providers.base import ProviderRequestError
    from henk.security.proxy import SecurityProxy
    from henk.skills import SkillRunner, SkillSelector
    from henk.task_display import TaskDisplay
    from henk.tools.code_runner import CodeRunnerTool
    from henk.tools.file_manager import FileManagerTool
    from henk.tools.memory_write import MemoryWriteTool
    from henk.tools.web_search import WebSearchTool
    from henk.transcript import TranscriptWriter

    _, staging, _, retrieval = _build_memory_services(config)
    transcript = TranscriptWriter(config.logs_dir)
    router = ModelRouter(config)
    model_gateway = ModelGateway(router, transcript)
    skill_selector = SkillSelector(config.skills_dir, model_gateway) if config.skills_enabled else None
    brain = Brain(config, model_gateway=model_gateway, memory_retrieval=retrieval, skill_selector=skill_selector)
    gateway = Gateway(config, brain, transcript)
    proxy = SecurityProxy(config.proxy_allowed_domains, config.proxy_allowed_methods)

    heartbeat = Heartbeat(interval_seconds=config.heartbeat_interval)

    def on_reminder(message: str):
        console.print(f"\n[yellow]⏰ Herinnering: {message}[/yellow]\n")

    if config.heartbeat_enabled:
        heartbeat.start(on_reminder)

    tools = {
        "web_search": WebSearchTool(proxy=proxy, timeout_seconds=config.web_search_timeout_seconds),
        "file_manager": FileManagerTool([str(path) for path in config.file_manager_read_roots], config.workspace_dir),
        "code_runner": CodeRunnerTool(config.workspace_dir, config.code_runner_timeout_seconds),
        "memory_write": MemoryWriteTool(staging),
        "reminder": ReminderTool(heartbeat=heartbeat),
    }
    react_loop = ReactLoop(brain=brain, gateway=gateway, tools=tools)
    skill_runner = SkillRunner(brain, gateway, react_loop)
    gateway.set_react_loop(react_loop)
    task_display = TaskDisplay(console, gateway)

    hard = config.control_dir / "hard_stop"
    if hard.exists() and hard.read_text(encoding="utf-8").strip().lower() == "true":
        console.print("[red]Henk is gestopt. Typ /resume om te hervatten.[/red]")

    try:
        print_henk(console, gateway.get_greeting(), gateway)
    except Exception:
        print_henk(console, "Hoi. Wat kan ik voor je doen?", gateway)

    startup_message = _startup_missing_key_message(router)
    if startup_message:
        print_henk(console, startup_message, gateway)

    key_bindings, shift_enter_supported = _build_key_bindings()
    if not shift_enter_supported:
        console.print("[dim]Shift+Enter wordt in deze terminal niet apart herkend. Typ /help voor uitleg.[/dim]\n")

    def _bottom_toolbar():
        return HTML(_build_bottom_toolbar_markup(gateway))

    session = PromptSession(
        completer=_build_completer(),
        auto_suggest=SlashCommandAutoSuggest(),
        style=PROMPT_STYLE,
        complete_while_typing=False,
        key_bindings=key_bindings,
        multiline=True,
        prompt_continuation="  ",
        bottom_toolbar=_bottom_toolbar,
    )

    def _on_token_usage(tokens_in: int, tokens_out: int) -> None:
        gateway.record_token_usage(tokens_in, tokens_out)
        if getattr(session, "app", None) is not None:
            session.app.invalidate()

    model_gateway.on_token_usage = _on_token_usage
    command_context = {
        "brain": brain,
        "router": router,
        "gateway": gateway,
        "react_loop": react_loop,
        "shift_enter_supported": shift_enter_supported,
    }

    task_queue: asyncio.Queue = asyncio.Queue()
    result_queue: asyncio.Queue = asyncio.Queue()
    active_tasks: dict[str, object] = {}

    work_task = asyncio.create_task(
        _work_loop(
            brain=brain,
            gateway=gateway,
            react_loop=react_loop,
            skill_runner=skill_runner,
            skill_selector=skill_selector,
            config=config,
            task_queue=task_queue,
            result_queue=result_queue,
            task_display=task_display,
            transcript=transcript,
        )
    )
    result_task = asyncio.create_task(
        _result_loop(
            result_queue=result_queue,
            console=console,
            gateway=gateway,
            task_display=task_display,
            session=session,
            active_tasks=active_tasks,
        )
    )
    try:
        await _conversation_loop(
            brain=brain,
            gateway=gateway,
            task_queue=task_queue,
            config=config,
            console=console,
            session=session,
            task_display=task_display,
            skill_selector=skill_selector,
            staging=staging,
            command_context=command_context,
            active_tasks=active_tasks,
        )
    except KeyboardInterrupt:
        pass
    finally:
        work_task.cancel()
        result_task.cancel()
        try:
            await work_task
        except asyncio.CancelledError:
            pass
        try:
            await result_task
        except asyncio.CancelledError:
            pass
        heartbeat.stop()

    console.print(f"\nTranscript bewaard in {transcript.file_path}")
