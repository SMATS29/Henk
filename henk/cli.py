"""CLI: henk init en henk chat."""

from __future__ import annotations

import shutil
from pathlib import Path

import typer
from rich.console import Console
from rich.theme import Theme

from henk.config import load_config

app = typer.Typer(help="Henk - Persoonlijke AI Orchestrator")
console = Console(theme=Theme({"henk": "cyan"}))


def _get_data_dir() -> Path:
    return Path.home() / "henk"


def _control_path(name: str) -> Path:
    return _get_data_dir() / "control" / name


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
        data_dir / "memory" / ".staged",
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
    console.print(f"Workspace:   {workspace} ({file_count} bestanden)")
    console.print(f"Laatste log: {latest_log}")


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

    if not config.api_key:
        console.print(
            f"[red]{config.api_key_env_var} niet gevonden.[/red]\n"
            "Maak een .env bestand aan met je API key. Zie .env.example."
        )
        raise typer.Exit(code=1)

    from henk.brain import Brain
    from henk.gateway import Gateway, KillSwitchActive
    from henk.react_loop import ReactLoop
    from henk.security.proxy import SecurityProxy
    from henk.tools.code_runner import CodeRunnerTool
    from henk.tools.file_manager import FileManagerTool
    from henk.tools.web_search import WebSearchTool
    from henk.transcript import TranscriptWriter

    transcript = TranscriptWriter(config.logs_dir)
    brain = Brain(config)
    gateway = Gateway(config, brain, transcript)
    proxy = SecurityProxy(config.proxy_allowed_domains, config.proxy_allowed_methods)
    tools = {
        "web_search": WebSearchTool(proxy=proxy, timeout_seconds=config.web_search_timeout_seconds),
        "file_manager": FileManagerTool([str(p) for p in config.file_manager_read_roots], config.workspace_dir),
        "code_runner": CodeRunnerTool(config.workspace_dir, config.code_runner_timeout_seconds),
    }
    react_loop = ReactLoop(brain=brain, gateway=gateway, tools=tools)
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

    console.print(f"\nTranscript bewaard in {transcript.file_path}")


if __name__ == "__main__":
    app()
