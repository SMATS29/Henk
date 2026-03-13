"""CLI: henk init en henk chat."""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

import typer
from rich.console import Console
from rich.theme import Theme

from henk.config import load_config
from henk.router import ModelRole, ModelRouter
from henk.requirements import Requirements, RequirementsStatus
from henk.skills import SkillRunner, SkillSelector
from henk.heartbeat import Heartbeat, ReminderTool
from henk.memory import ChangeType, MemoryRetrieval, MemoryStore, Provenance, RelevanceScorer, StagedChange, StagingManager

app = typer.Typer(help="Henk - Persoonlijke AI Orchestrator")
console = Console(theme=Theme({"henk": "cyan"}))


def _get_data_dir() -> Path:
    return Path.home() / "henk"


def _control_path(name: str) -> Path:
    return _get_data_dir() / "control" / name


def _build_memory_services(config):
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


@app.command()
def init():
    """Initialiseer Henk's data directory."""
    data_dir = _get_data_dir()

    if data_dir.exists():
        overwrite = typer.confirm(f"{data_dir} bestaat al. Opnieuw initialiseren?", default=False)
        if not overwrite:
            typer.echo("Init afgebroken.")
            raise typer.Exit()

    dirs = [
        data_dir / "memory" / "active",
        data_dir / "memory" / "episodes",
        data_dir / "memory" / ".staged" / "pending",
        data_dir / "memory" / ".staged" / "archive",
        data_dir / "workspace",
        data_dir / "skills",
        data_dir / "control",
        data_dir / "tools" / "user",
        data_dir / "tools" / "generated",
        data_dir / "tools" / "external",
        data_dir / "logs",
    ]
    for directory in dirs:
        directory.mkdir(parents=True, exist_ok=True)

    core_md = data_dir / "memory" / "core.md"
    if not core_md.exists():
        core_md.write_text("# Henk - Kerngeheugen\n", encoding="utf-8")

    config_dest = data_dir / "henk.yaml"
    if not config_dest.exists():
        default_config = Path(__file__).parent.parent / "henk.yaml.default"
        if default_config.exists():
            shutil.copy2(default_config, config_dest)

    for name in ("graceful_stop", "hard_stop"):
        ctrl_file = data_dir / "control" / name
        ctrl_file.write_text("false", encoding="utf-8")

    console.print("[bold green]Henk is geinitialiseerd.[/bold green] Start met: [bold]henk chat[/bold]")


@app.command()
def stop(clear: bool = typer.Option(False, "--clear", help="Wis workspace bestanden na stop")):
    """Activeer hard stop voor Henk."""
    data_dir = _get_data_dir()
    _control_path("hard_stop").parent.mkdir(parents=True, exist_ok=True)
    _control_path("hard_stop").write_text("true", encoding="utf-8")
    if clear:
        workspace = data_dir / "workspace"
        if workspace.exists():
            for item in workspace.iterdir():
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink(missing_ok=True)
        console.print("Henk is gestopt. Werkbestanden gewist.")
        return
    console.print("Henk is gestopt.")


@app.command()
def pause():
    """Pauzeer nieuwe taken."""
    _control_path("graceful_stop").parent.mkdir(parents=True, exist_ok=True)
    _control_path("graceful_stop").write_text("true", encoding="utf-8")
    console.print("Henk is gepauzeerd. Geen nieuwe taken.")


@app.command()
def resume():
    """Hervat na een pause."""
    _control_path("graceful_stop").parent.mkdir(parents=True, exist_ok=True)
    _control_path("graceful_stop").write_text("false", encoding="utf-8")
    console.print("Henk is hervat.")


@app.command()
def status():
    """Toon status van gateway, kill switch en logs."""
    data_dir = _get_data_dir()
    hard = _control_path("hard_stop").read_text(encoding="utf-8").strip().lower() == "true" if _control_path("hard_stop").exists() else False
    graceful = _control_path("graceful_stop").read_text(encoding="utf-8").strip().lower() == "true" if _control_path("graceful_stop").exists() else False
    if hard:
        state = "gestopt"
    elif graceful:
        state = "gepauzeerd"
    else:
        state = "normaal"

    workspace = data_dir / "workspace"
    file_count = 0
    if workspace.exists():
        file_count = sum(1 for _ in workspace.rglob("*"))

    logs_dir = data_dir / "logs"
    latest_log = "geen"
    if logs_dir.exists():
        logs = sorted(logs_dir.glob("transcript_*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        if logs:
            latest_log = str(logs[0])

    console.print("Gateway:     actief (embedded in CLI)")
    console.print(f"Kill switch: {state}")
    config = load_config(data_dir)
    router = ModelRouter(config)
    try:
        default_provider = router.get_provider(ModelRole.DEFAULT)
        fallback = ", ".join(router.describe_role_chain(ModelRole.DEFAULT)[1:]) or "geen"
        console.print(f"Provider:    {router.provider_label(default_provider)} (DEFAULT)")
        console.print(f"Fallback:    {fallback}")
    except RuntimeError:
        console.print("Provider:    geen provider beschikbaar")
        console.print("Fallback:    geen")
    console.print(f"Workspace:   {workspace} ({file_count} bestanden)")
    console.print(f"Laatste log: {latest_log}")


@app.command()
def config(
    show: bool = typer.Option(False, "--show", help="Toon huidige configuratie"),
    set_limit: str | None = typer.Option(None, "--set", help="Stel limiet in, bijv. 'max_tool_calls=8'"),
):
    """Bekijk of wijzig Henk's configuratie."""
    data_dir = _get_data_dir()
    cfg = load_config(data_dir)

    if set_limit:
        key, _, value = set_limit.partition("=")
        if not key or not value:
            raise typer.BadParameter("Gebruik formaat key=value")
        valid_keys = {"max_tool_calls", "max_retries_content", "max_retries_technical"}
        if key not in valid_keys:
            raise typer.BadParameter(f"Onbekende limiet '{key}'")
        try:
            parsed = int(value)
        except ValueError as exc:
            raise typer.BadParameter("Waarde moet een integer zijn") from exc

        import yaml

        config_path = data_dir / "henk.yaml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        content = {}
        if config_path.exists():
            content = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        content.setdefault("security", {}).setdefault("react_loop", {})[key] = parsed
        config_path.write_text(yaml.safe_dump(content, sort_keys=False, allow_unicode=True), encoding="utf-8")
        console.print(f"{key} ingesteld op {parsed}")
        return

    if show or not set_limit:
        router = ModelRouter(cfg)
        console.print("[bold]Rollen:[/bold]")
        for role in ModelRole:
            try:
                provider = router.get_provider(role)
                console.print(f"  {role.value}: {router.provider_label(provider)}")
            except RuntimeError:
                console.print(f"  {role.value}: [red]geen provider beschikbaar[/red]")

        console.print("\n[bold]Limieten:[/bold]")
        console.print(f"  max_tool_calls: {cfg.max_tool_calls}")
        console.print(f"  max_retries_content: {cfg.max_retries_content}")
        console.print(f"  max_retries_technical: {cfg.max_retries_technical}")


@app.command()
def review():
    """Review staged geheugenwijzigingen en archiveringskandidaten."""
    data_dir = _get_data_dir()
    if not data_dir.exists():
        console.print("[red]Henk is nog niet geinitialiseerd.[/red] Voer eerst uit: [bold]henk init[/bold]")
        raise typer.Exit(code=1)

    config = load_config(data_dir)
    store, staging, scorer, retrieval = _build_memory_services(config)
    pending_changes = staging.list_pending()

    if not pending_changes:
        console.print("Geen staged geheugenwijzigingen.")

    for change in pending_changes:
        preview = " ".join(change.proposed_content.split())[:300]
        console.print(f"\n[bold]{change.id}[/bold] [{change.change_type.value}]")
        console.print(f"Herkomst: {change.provenance.value}")
        console.print(f"Reden: {change.reason}")
        console.print(f"Inhoud: {preview}")
        if change.suspicious:
            console.print("[bold red]Waarschuwing: verdacht geheugenvoorstel.[/bold red]")
        if typer.confirm("Goedkeuren?", default=not change.suspicious):
            staging.approve(change.id)
            console.print("[green]Goedgekeurd.[/green]")
        else:
            staging.reject(change.id)
            console.print("[yellow]Afgekeurd.[/yellow]")

    active_items = store.list_items("active") + store.list_items("episodes")
    original_scores = {item.id: item.score for item in active_items}
    scorer.apply_decay(active_items)
    for item in active_items:
        if item.score != original_scores[item.id]:
            store.save_item(item)

    archive_candidates = scorer.get_archive_candidates(active_items)
    if archive_candidates:
        console.print("\n[bold]Archiveringskandidaten[/bold]")
    for item in archive_candidates:
        console.print(f"- {item.title} ({item.score}) [{item.path}]")
        if typer.confirm("Archiveren?", default=False):
            store.archive_item(item)
            console.print("[green]Gearchiveerd.[/green]")

    retrieval.rebuild_index()
    console.print("\nReview afgerond.")


@app.command()
def chat():
    """Start een interactieve chatsessie met Henk."""
    data_dir = _get_data_dir()

    if not data_dir.exists():
        console.print("[red]Henk is nog niet geinitialiseerd.[/red] Voer eerst uit: [bold]henk init[/bold]")
        raise typer.Exit(code=1)

    config = load_config(data_dir)

    if _control_path("hard_stop").exists() and _control_path("hard_stop").read_text(encoding="utf-8").strip().lower() == "true":
        console.print("[red]Henk is gestopt. Gebruik 'henk resume' of reset hard_stop handmatig.[/red]")
        raise typer.Exit(code=1)

    if _control_path("graceful_stop").exists() and _control_path("graceful_stop").read_text(encoding="utf-8").strip().lower() == "true":
        console.print("[yellow]Henk staat op pauze. Nieuwe taken worden geweigerd.[/yellow]")

    from henk.brain import Brain
    from henk.gateway import Gateway, KillSwitchActive
    from henk.react_loop import ReactLoop
    from henk.security.proxy import SecurityProxy
    from henk.tools.code_runner import CodeRunnerTool
    from henk.tools.file_manager import FileManagerTool
    from henk.tools.memory_write import MemoryWriteTool
    from henk.tools.web_search import WebSearchTool
    from henk.transcript import TranscriptWriter

    _, staging, _, retrieval = _build_memory_services(config)
    transcript = TranscriptWriter(config.logs_dir)
    skill_selector = SkillSelector(config.skills_dir, ModelRouter(config)) if config.skills_enabled else None
    brain = Brain(config, memory_retrieval=retrieval, skill_selector=skill_selector)
    gateway = Gateway(config, brain, transcript)
    proxy = SecurityProxy(config.proxy_allowed_domains, config.proxy_allowed_methods)

    heartbeat = Heartbeat(interval_seconds=config.heartbeat_interval)

    def on_reminder(message: str):
        console.print(f"\n[yellow]⏰ Herinnering: {message}[/yellow]\n[bold]Henk > [/bold]", end="")

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

    try:
        greeting = gateway.get_greeting()
        console.print(f"[henk]{greeting}[/henk]\n")
    except Exception:
        console.print("[henk]Hoi. Wat kan ik voor je doen?[/henk]\n")

    try:
        while True:
            try:
                user_input = console.input("[bold]Henk > [/bold]")
            except EOFError:
                break

            if user_input.strip().lower() in ("exit", "quit"):
                break

            if not user_input.strip():
                continue

            try:
                if brain.active_requirements and brain.active_requirements.status == RequirementsStatus.CONFIRMED:
                    requirements = brain.active_requirements
                    requirements.start_execution()
                    if requirements.skill_name and skill_selector:
                        skill = skill_selector.select(requirements.task_description)
                        if skill:
                            result = skill_runner.run(skill, requirements)
                        else:
                            result = react_loop.run(requirements.task_description)
                    else:
                        result = react_loop.run(requirements.task_description + "\n\nEisen:\n" + requirements.specifications)
                    requirements.complete(result)
                    brain.active_requirements = None
                    response = result
                elif brain.active_requirements:
                    response = brain.refine_requirements(user_input, brain.active_requirements)
                else:
                    kind = brain.classify_input(user_input)
                    if kind == "taak":
                        req = Requirements(task_description=user_input)
                        if skill_selector:
                            skill = skill_selector.select(user_input)
                            if skill:
                                req.skill_name = skill.name
                        brain.active_requirements = req
                        response = brain.refine_requirements(user_input, req)
                    else:
                        response = gateway.process(user_input)

                if response:
                    console.print(f"[henk]{response}[/henk]\n")
            except KillSwitchActive as error:
                console.print(f"[red]Henk is gestopt ({error.switch_type}).[/red]")
                break
            except Exception:
                console.print(
                    "[henk]Ik kan even niet bij mijn brein. "
                    "Check je API key of internetverbinding.[/henk]\n"
                )

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
                    reason="Automatische sessiesamenvatting bij afsluiten van henk chat.",
                    timestamp=datetime.now(timezone.utc),
                    proposed_title=f"Sessie {today}",
                    target_path=f"episodes/{today}.md",
                )
            )
            console.print("[dim]Sessie-samenvatting in staging gezet.[/dim]")

    console.print(f"\nTranscript bewaard in {transcript.file_path}")


if __name__ == "__main__":
    app()
