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
        else:
            config_dest.write_text(
                "henk:\n  name: Henk\n  language: nl\n\n"
                "provider:\n  default: openai\n  model: gpt-5-mini\n\n"
                "security:\n  react_loop:\n    max_tool_calls: 4\n    max_retries_content: 2\n"
                "    max_retries_technical: 1\n    identical_call_detection: true\n\n"
                "ui:\n  pipe_name: henk-gateway\n  history_hours: 24\n\n"
                "paths:\n  data_dir: ~/henk\n  memory_dir: ~/henk/memory\n"
                "  workspace_dir: ~/henk/workspace\n  logs_dir: ~/henk/logs\n"
                "  control_dir: ~/henk/control\n",
                encoding="utf-8",
            )

    for name in ("graceful_stop", "hard_stop"):
        ctrl_file = data_dir / "control" / name
        ctrl_file.write_text("false", encoding="utf-8")

    console.print("[bold green]Henk is geinitialiseerd.[/bold green] Start met: [bold]henk chat[/bold]")


@app.command()
def chat():
    """Start een interactieve chatsessie met Henk."""
    data_dir = _get_data_dir()

    if not data_dir.exists():
        console.print("[red]Henk is nog niet geinitialiseerd.[/red] Voer eerst uit: [bold]henk init[/bold]")
        raise typer.Exit(code=1)

    config = load_config(data_dir)

    if not config.api_key:
        console.print(
            f"[red]{config.api_key_env_var} niet gevonden.[/red]\n"
            "Maak een .env bestand aan met je API key. Zie .env.example."
        )
        raise typer.Exit(code=1)

    from henk.brain import Brain
    from henk.gateway import Gateway, KillSwitchActive
    from henk.transcript import TranscriptWriter

    transcript = TranscriptWriter(config.logs_dir)
    brain = Brain(config)
    gateway = Gateway(config, brain, transcript)

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
