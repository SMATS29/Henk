"""CLI entrypoint voor Henk."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import typer
from rich.console import Console
from rich.theme import Theme

from henk.commands import handle_status
from henk.config import load_config

app = typer.Typer(help="Henk - Persoonlijke AI Orchestrator", invoke_without_command=True)
console = Console(theme=Theme({"henk": "cyan"}))


def _get_data_dir() -> Path:
    return Path.home() / "henk"


def _control_path(name: str) -> Path:
    return _get_data_dir() / "control" / name


def _do_init(data_dir: Path) -> None:
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
        (data_dir / "control" / name).write_text("false", encoding="utf-8")

    console.print("[bold green]Henk is geinitialiseerd.[/bold green]")


def _ensure_initialized() -> Path:
    data_dir = _get_data_dir()
    if not data_dir.exists():
        console.print("[dim]Eerste keer? Henk initialiseert zichzelf...[/dim]\n")
        _do_init(data_dir)
    return data_dir


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    """Start Henk. Zonder subcommand = open de chat."""
    if ctx.invoked_subcommand is not None:
        return

    data_dir = _ensure_initialized()
    config = load_config(data_dir)
    from henk.repl import start_repl

    asyncio.run(start_repl(config, console))


@app.command()
def init():
    """Initialiseer Henk handmatig."""
    data_dir = _get_data_dir()
    if data_dir.exists():
        overwrite = typer.confirm(f"{data_dir} bestaat al. Opnieuw initialiseren?", default=False)
        if not overwrite:
            raise typer.Exit()
    _do_init(data_dir)


@app.command()
def stop(clear: bool = typer.Option(False, "--clear", help="Wis workspace bestanden na stop")):
    """Hard stop vanuit terminal."""
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
    else:
        console.print("Henk is gestopt.")


@app.command()
def pause():
    """Pauzeer nieuwe taken."""
    _control_path("graceful_stop").parent.mkdir(parents=True, exist_ok=True)
    _control_path("graceful_stop").write_text("true", encoding="utf-8")
    console.print("Henk is gepauzeerd. Geen nieuwe taken.")


@app.command()
def resume():
    """Hervat na pause of stop."""
    _control_path("graceful_stop").parent.mkdir(parents=True, exist_ok=True)
    _control_path("graceful_stop").write_text("false", encoding="utf-8")
    _control_path("hard_stop").write_text("false", encoding="utf-8")
    console.print("Henk is hervat.")


@app.command()
def status():
    """Toon status vanuit terminal."""
    config = load_config(_get_data_dir())
    handle_status(config, console)


@app.command(hidden=True)
def chat():
    """Start chat (alias — gebruik gewoon 'henk')."""
    data_dir = _ensure_initialized()
    config = load_config(data_dir)
    from henk.repl import start_repl

    asyncio.run(start_repl(config, console))


if __name__ == "__main__":
    app()
