"""Interactieve REPL met prompt_toolkit autocomplete."""

from __future__ import annotations

from datetime import datetime, timezone

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style
from rich.console import Console

from henk.brain import Brain
from henk.commands import dispatch_command, get_command_names
from henk.config import Config
from henk.gateway import Gateway, KillSwitchActive
from henk.heartbeat import Heartbeat, ReminderTool
from henk.memory import ChangeType, MemoryRetrieval, MemoryStore, Provenance, RelevanceScorer, StagedChange, StagingManager
from henk.model_gateway import ModelGateway
from henk.output import print_henk
from henk.react_loop import ReactLoop
from henk.requirements import Requirements, RequirementsStatus
from henk.router import ModelRouter, ProviderSelectionError
from henk.router.providers.base import ProviderRequestError
from henk.security.proxy import SecurityProxy
from henk.skills import SkillRunner, SkillSelector
from henk.spinner import Spinner
from henk.tools.code_runner import CodeRunnerTool
from henk.tools.file_manager import FileManagerTool
from henk.tools.memory_write import MemoryWriteTool
from henk.tools.web_search import WebSearchTool
from henk.transcript import TranscriptWriter

PROMPT_STYLE = Style.from_dict({"prompt": "bold cyan"})


def _message_for_model_error(error: Exception) -> str:
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
        if error.reason == "network_unavailable":
            return "Ik kan het model nu niet bereiken. Check je internet of lokale modelserver."
        if error.reason == "authentication_failed":
            return "Ik kan het model niet gebruiken. Check je API key."
        if error.reason == "missing_credentials":
            return "Ik kan geen model bereiken omdat er geen API key is ingesteld."
        return "De modelaanroep mislukte. Probeer het zo nog eens."
    return "Ik kan even niet bij mijn brein. Check je API key of internetverbinding."


def _build_completer() -> WordCompleter:
    return WordCompleter(
        get_command_names(),
        sentence=True,
        meta_dict={
            "/stop": "Hard stop — alles stopt direct",
            "/pause": "Pauzeer — geen nieuwe taken",
            "/resume": "Hervat na pause of stop",
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


def _build_key_bindings() -> KeyBindings:
    bindings = KeyBindings()

    @bindings.add("enter")
    def handle_enter(event) -> None:
        event.current_buffer.validate_and_handle()

    @bindings.add("s-enter")
    def handle_shift_enter(event) -> None:
        event.current_buffer.insert_text("\n")

    return bindings


def start_repl(config: Config, console: Console) -> None:
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
    spinner = Spinner(console)

    hard = config.control_dir / "hard_stop"
    if hard.exists() and hard.read_text(encoding="utf-8").strip().lower() == "true":
        console.print("[red]Henk is gestopt. Typ /resume om te hervatten.[/red]")

    try:
        print_henk(console, gateway.get_greeting(), brain.token_tracker)
    except Exception:
        print_henk(console, "Hoi. Wat kan ik voor je doen?", brain.token_tracker)

    session = PromptSession(
        completer=_build_completer(),
        style=PROMPT_STYLE,
        complete_while_typing=False,
        key_bindings=_build_key_bindings(),
        multiline=True,
        prompt_continuation="  ",
    )
    command_context = {"brain": brain, "router": router, "gateway": gateway, "react_loop": react_loop}

    try:
        while True:
            try:
                user_input = session.prompt(HTML("<prompt>❯ </prompt>"), completer=_build_completer())
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
                if brain.active_requirements and brain.active_requirements.status == RequirementsStatus.CONFIRMED:
                    requirements = brain.active_requirements
                    requirements.start_execution()
                    if requirements.skill_name and skill_selector:
                        skill = skill_selector.select(requirements.task_description)
                        if skill:
                            spinner.start("Henk denkt...")
                            response = skill_runner.run(skill, requirements, on_status=spinner.update)
                            spinner.stop()
                        else:
                            spinner.start("Henk denkt...")
                            response = react_loop.run(requirements.task_description, on_status=spinner.update)
                            spinner.stop()
                    else:
                        spinner.start("Henk denkt...")
                        response = react_loop.run(
                            requirements.task_description + "\n\nEisen:\n" + requirements.specifications,
                            on_status=spinner.update,
                        )
                        spinner.stop()
                    requirements.complete(response)
                    brain.active_requirements = None
                elif brain.active_requirements:
                    spinner.start("Henk denkt...")
                    response = brain.refine_requirements(stripped, brain.active_requirements)
                    spinner.stop()
                else:
                    spinner.start("Henk denkt...")
                    kind = brain.classify_input(stripped)
                    if kind == "taak":
                        req = Requirements(task_description=stripped)
                        if skill_selector:
                            skill = skill_selector.select(stripped)
                            if skill:
                                req.skill_name = skill.name
                        brain.active_requirements = req
                        response = brain.refine_requirements(stripped, req)
                    else:
                        response = gateway.process(stripped, on_status=spinner.update)
                    spinner.stop()

                if response:
                    print_henk(console, response, brain.token_tracker)
            except KillSwitchActive as error:
                spinner.stop()
                console.print(f"[red]Henk is gestopt ({error.switch_type}). Typ /resume om te hervatten.[/red]")
            except (ProviderSelectionError, ProviderRequestError) as error:
                spinner.stop()
                console.print(f"[red]{_message_for_model_error(error)}[/red]\n")
            except Exception:
                spinner.stop()
                console.print("[red]Ik kan even niet bij mijn brein. Check je API key of internetverbinding.[/red]\n")
    except KeyboardInterrupt:
        pass
    finally:
        heartbeat.stop()

    if brain.has_history:
        summary = brain.summarize_session()
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

    console.print(f"\nTranscript bewaard in {transcript.file_path}")
