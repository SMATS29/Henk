# Henk CLI UX Overhaul — Bouwinstructie voor Claude Code

## Context

Henk is een persoonlijke AI-orchestrator (v0.5). De CLI werkt maar voelt niet als een modern tool. Dit is een UX-upgrade die de CLI verandert naar een ervaring zoals Claude Code of Codex: je typt `henk`, je bent in gesprek, slash-commands voor alles.

## Wat er verandert

### Voor deze wijziging

```
> henk chat          # Start gesprek
> henk init          # Initialiseer
> henk stop          # Stop
> henk status        # Toon status
```

### Na deze wijziging

```
> henk               # Start gesprek (auto-init bij eerste keer)
> /stop              # In de chat: hard stop
> /status            # In de chat: toon status
> /help              # In de chat: toon alle commands
> /exit              # In de chat: sluit af

> henk stop          # Vanuit terminal (zonder Henk te openen)
> henk status        # Vanuit terminal
```

## Nieuwe dependency

Voeg `prompt_toolkit` toe aan pyproject.toml:

```toml
dependencies = [
    # ... bestaande ...
    "prompt_toolkit>=3.0.0",
]
```

`prompt_toolkit` vervangt Rich’s `console.input()` voor de REPL-input. Rich blijft voor output-formatting.

## Nieuwe bestanden

```
henk/
├── henk/
│   ├── repl.py                 # REPL: input loop met prompt_toolkit
│   ├── commands.py             # Slash-command definities en handlers
```

## Gewijzigde bestanden

```
henk/
├── henk/
│   ├── cli.py                  # Vereenvoudigd: henk = chat, subcommands behouden
```

## cli.py — Nieuwe structuur

De Typer app wordt vereenvoudigd. `henk` zonder argument start de REPL. Een paar subcommands blijven beschikbaar voor gebruik buiten de REPL.

```python
"""CLI entrypoint voor Henk."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from henk.config import load_config

app = typer.Typer(
    help="Henk — Persoonlijke AI Orchestrator",
    invoke_without_command=True,    # henk zonder argument triggert callback
)
console = Console()


def _get_data_dir() -> Path:
    return Path.home() / "henk"


def _ensure_initialized() -> Path:
    """Zorg dat Henk is geïnitialiseerd. Auto-init bij eerste keer."""
    data_dir = _get_data_dir()
    if not data_dir.exists():
        console.print("[dim]Eerste keer? Henk initialiseert zichzelf...[/dim]\n")
        _do_init(data_dir)
    return data_dir


def _do_init(data_dir: Path) -> None:
    """Voer de initialisatie uit (gedeelde logica)."""
    import shutil

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
        core_md.write_text("# Henk — Kerngeheugen\n", encoding="utf-8")

    config_dest = data_dir / "henk.yaml"
    if not config_dest.exists():
        default_config = Path(__file__).parent.parent / "henk.yaml.default"
        if default_config.exists():
            shutil.copy2(default_config, config_dest)

    for name in ("graceful_stop", "hard_stop"):
        ctrl = data_dir / "control" / name
        ctrl.write_text("false", encoding="utf-8")

    console.print("[bold green]Henk is geïnitialiseerd.[/bold green]\n")


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    """Start Henk. Zonder subcommand = open de chat."""
    if ctx.invoked_subcommand is not None:
        return  # Een subcommand is aangeroepen, laat dat afhandelen

    # henk zonder argument = start de REPL
    data_dir = _ensure_initialized()
    config = load_config(data_dir)

    if not config.api_key:
        console.print(
            f"[red]{config.api_key_env_var} niet gevonden.[/red]\n"
            "Maak een .env bestand aan met je API key."
        )
        raise typer.Exit(code=1)

    from henk.repl import start_repl
    start_repl(config, console)


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
def stop(clear: bool = typer.Option(False, "--clear", help="Wis workspace na stop")):
    """Hard stop vanuit terminal."""
    data_dir = _get_data_dir()
    (data_dir / "control" / "hard_stop").write_text("true", encoding="utf-8")
    if clear:
        import shutil
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
def status():
    """Toon status vanuit terminal."""
    from henk.commands import handle_status
    data_dir = _get_data_dir()
    config = load_config(data_dir)
    handle_status(config, console)
```

## commands.py — Slash-command handlers

Alle slash-command logica op één plek. Zowel de REPL als cli.py gebruiken dezelfde handlers.

```python
"""Slash-command definities en handlers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from rich.console import Console

from henk.config import Config


@dataclass
class SlashCommand:
    """Definitie van een slash-command."""
    name: str               # Zonder slash, bijv. "stop"
    description: str        # Korte beschrijving voor /help en autocomplete
    handler: str            # Naam van de handler-functie


# Alle beschikbare commands
COMMANDS: list[SlashCommand] = [
    SlashCommand("stop", "Hard stop — alles stopt direct", "handle_stop"),
    SlashCommand("pause", "Pauzeer — geen nieuwe taken", "handle_pause"),
    SlashCommand("resume", "Hervat na pause of stop", "handle_resume"),
    SlashCommand("status", "Toon status van Henk", "handle_status"),
    SlashCommand("review", "Dagelijkse memory review", "handle_review"),
    SlashCommand("config", "Bekijk configuratie", "handle_config"),
    SlashCommand("help", "Toon beschikbare commands", "handle_help"),
    SlashCommand("exit", "Sluit Henk af", "handle_exit"),
    SlashCommand("clear", "Wis het scherm", "handle_clear"),
    SlashCommand("history", "Toon gespreksgeschiedenis", "handle_history"),
]


def get_command_names() -> list[str]:
    """Alle command-namen voor autocomplete."""
    return [f"/{cmd.name}" for cmd in COMMANDS]


def handle_stop(config: Config, console: Console, **kwargs) -> str | None:
    """Hard stop."""
    control = config.control_dir
    (control / "hard_stop").write_text("true", encoding="utf-8")
    console.print("[red]Henk is gestopt.[/red]")
    return "exit"  # Signaal om de REPL te verlaten


def handle_pause(config: Config, console: Console, **kwargs) -> str | None:
    """Graceful stop."""
    control = config.control_dir
    (control / "graceful_stop").write_text("true", encoding="utf-8")
    console.print("[yellow]Henk is gepauzeerd. Geen nieuwe taken.[/yellow]")
    return None


def handle_resume(config: Config, console: Console, **kwargs) -> str | None:
    """Hervat na pause of stop."""
    control = config.control_dir
    (control / "graceful_stop").write_text("false", encoding="utf-8")
    (control / "hard_stop").write_text("false", encoding="utf-8")
    console.print("[green]Henk is hervat.[/green]")
    return None


def handle_status(config: Config, console: Console, **kwargs) -> str | None:
    """Toon status."""
    hard = _read_switch(config, "hard_stop")
    graceful = _read_switch(config, "graceful_stop")

    if hard:
        state = "[red]gestopt[/red]"
    elif graceful:
        state = "[yellow]gepauzeerd[/yellow]"
    else:
        state = "[green]normaal[/green]"

    workspace = config.workspace_dir
    file_count = sum(1 for _ in workspace.rglob("*")) if workspace.exists() else 0

    logs_dir = config.logs_dir
    latest_log = "geen"
    if logs_dir.exists():
        logs = sorted(logs_dir.glob("transcript_*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        if logs:
            latest_log = str(logs[0].name)

    console.print(f"  Kill switch:  {state}")
    console.print(f"  Workspace:    {file_count} bestanden")
    console.print(f"  Laatste log:  {latest_log}")

    # Toon provider info als router beschikbaar is
    router = kwargs.get("router")
    if router:
        try:
            from henk.router.router import ModelRole
            for role in ModelRole:
                try:
                    provider = router.get_provider(role)
                    console.print(f"  {role.value:10s}  {provider.name}/{provider._model}")
                except Exception:
                    console.print(f"  {role.value:10s}  [red]niet beschikbaar[/red]")
        except ImportError:
            pass

    return None


def handle_review(config: Config, console: Console, **kwargs) -> str | None:
    """Memory review."""
    # Importeer en voer de bestaande review-logica uit
    from henk.memory.store import MemoryStore
    from henk.memory.staging import StagingManager
    from henk.memory.scoring import RelevanceScorer

    store = MemoryStore(config.memory_dir)
    staging = StagingManager(config.memory_dir / ".staged", store)

    pending = staging.list_pending()
    if not pending:
        console.print("[dim]Geen openstaande geheugenwijzigingen.[/dim]")
        return None

    console.print(f"\n[bold]{len(pending)} wijziging(en) wachten op review:[/bold]\n")

    import typer
    for change in pending:
        if change.suspicious:
            console.print(f"  [red]⚠ VERDACHT[/red]")
        console.print(f"  Type:     {change.change_type.value}")
        console.print(f"  Herkomst: {change.provenance.value}")
        console.print(f"  Reden:    {change.reason}")
        console.print(f"  Inhoud:   {change.proposed_content[:200]}...")

        approved = typer.confirm("  Goedkeuren?", default=not change.suspicious)
        if approved:
            staging.approve(change.id)
            console.print("  [green]✓ Goedgekeurd[/green]\n")
        else:
            staging.reject(change.id)
            console.print("  [red]✗ Afgewezen[/red]\n")

    console.print("[dim]Review afgerond.[/dim]")
    return None


def handle_config(config: Config, console: Console, **kwargs) -> str | None:
    """Toon configuratie."""
    console.print(f"  Provider:              {config.provider}")
    console.print(f"  Model:                 {config.model}")
    console.print(f"  Max tool-calls:        {config.max_tool_calls}")
    console.print(f"  Max retries (content): {config.max_retries_content}")
    console.print(f"  Max retries (tech):    {config.max_retries_technical}")
    console.print(f"  Data dir:              {config.data_dir}")
    return None


def handle_help(config: Config, console: Console, **kwargs) -> str | None:
    """Toon beschikbare commands."""
    console.print("\n[bold]Beschikbare commands:[/bold]\n")
    for cmd in COMMANDS:
        console.print(f"  [cyan]/{cmd.name:10s}[/cyan] {cmd.description}")
    console.print()
    return None


def handle_exit(config: Config, console: Console, **kwargs) -> str | None:
    """Sluit af."""
    return "exit"


def handle_clear(config: Config, console: Console, **kwargs) -> str | None:
    """Wis het scherm."""
    console.clear()
    return None


def handle_history(config: Config, console: Console, **kwargs) -> str | None:
    """Toon gespreksgeschiedenis."""
    brain = kwargs.get("brain")
    if not brain or not brain._history:
        console.print("[dim]Nog geen gesprek in deze sessie.[/dim]")
        return None

    console.print("\n[bold]Gespreksgeschiedenis:[/bold]\n")
    for msg in brain._history:
        role = msg.get("role", "?")
        content = msg.get("content", "")
        if isinstance(content, str):
            preview = content[:150]
            if role == "user":
                console.print(f"  [bold]Jij:[/bold] {preview}")
            else:
                console.print(f"  [cyan]Henk:[/cyan] {preview}")
    console.print()
    return None


def _read_switch(config: Config, name: str) -> bool:
    path = config.control_dir / name
    if path.exists():
        return path.read_text(encoding="utf-8").strip().lower() == "true"
    return False


def dispatch_command(command: str, config: Config, console: Console, **kwargs) -> str | None:
    """Voer een slash-command uit. Return 'exit' om de REPL te verlaten, None om door te gaan."""
    cmd_name = command.lstrip("/").strip().split()[0].lower()

    handlers = {
        "stop": handle_stop,
        "pause": handle_pause,
        "resume": handle_resume,
        "status": handle_status,
        "review": handle_review,
        "config": handle_config,
        "help": handle_help,
        "exit": handle_exit,
        "clear": handle_clear,
        "history": handle_history,
    }

    handler = handlers.get(cmd_name)
    if handler:
        return handler(config, console, **kwargs)

    console.print(f"[red]Onbekend command: /{cmd_name}[/red] — typ /help voor opties.")
    return None
```

## repl.py — De REPL met prompt_toolkit

Dit is het hart van de nieuwe UX.

```python
"""Interactieve REPL met prompt_toolkit autocomplete."""

from __future__ import annotations

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.styles import Style
from rich.console import Console

from henk.commands import dispatch_command, get_command_names
from henk.config import Config


# Prompt styling
PROMPT_STYLE = Style.from_dict({
    "prompt": "bold cyan",
})


def _build_completer() -> WordCompleter:
    """Bouw autocomplete voor slash-commands."""
    return WordCompleter(
        get_command_names(),
        sentence=True,          # Match hele input, niet per woord
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


def start_repl(config: Config, console: Console) -> None:
    """Start de interactieve REPL."""
    # Initialiseer alle componenten (bestaande logica uit cli.py chat)
    from henk.brain import Brain
    from henk.gateway import Gateway, KillSwitchActive
    from henk.react_loop import ReactLoop
    from henk.transcript import TranscriptWriter

    # Import tool en memory componenten
    # (pas aan op basis van wat er in de huidige codebase staat)
    from henk.security.proxy import SecurityProxy
    from henk.tools.web_search import WebSearchTool
    from henk.tools.file_manager import FileManagerTool
    from henk.tools.code_runner import CodeRunnerTool

    # Initialiseer componenten
    transcript = TranscriptWriter(config.logs_dir)

    # Router (v0.4)
    try:
        from henk.router.router import ModelRouter
        router = ModelRouter(config)
    except ImportError:
        router = None

    # Memory (v0.3)
    try:
        from henk.memory.store import MemoryStore
        from henk.memory.staging import StagingManager
        from henk.memory.retrieval import MemoryRetrieval
        store = MemoryStore(config.memory_dir)
        staging = StagingManager(config.memory_dir / ".staged", store)
        retrieval = MemoryRetrieval(store, config) if config.memory_vector_enabled else None
    except ImportError:
        staging = None
        retrieval = None

    # Brain
    brain = Brain(config, router=router, memory_retrieval=retrieval)
    gateway = Gateway(config, brain, transcript)

    # Tools
    proxy = SecurityProxy(config.proxy_allowed_domains, config.proxy_allowed_methods)
    tools = {
        "web_search": WebSearchTool(proxy=proxy, timeout_seconds=config.web_search_timeout_seconds),
        "file_manager": FileManagerTool([str(p) for p in config.file_manager_read_roots], config.workspace_dir),
        "code_runner": CodeRunnerTool(config.workspace_dir, config.code_runner_timeout_seconds),
    }

    # Memory write tool (v0.3)
    if staging:
        try:
            from henk.tools.memory_write import MemoryWriteTool
            tools["memory_write"] = MemoryWriteTool(staging=staging)
        except ImportError:
            pass

    # Reminder tool (v0.5)
    try:
        from henk.heartbeat import Heartbeat, ReminderTool
        heartbeat = Heartbeat(interval_seconds=config.heartbeat_interval)

        def on_reminder(message: str):
            console.print(f"\n[yellow]⏰ {message}[/yellow]\n")

        heartbeat.start(on_reminder)
        tools["reminder"] = ReminderTool(heartbeat=heartbeat)
    except ImportError:
        heartbeat = None

    # Skill selector (v0.5)
    try:
        from henk.skills.selector import SkillSelector
        from henk.skills.runner import SkillRunner
        skill_selector = SkillSelector(config.skills_dir, router) if router else None
        skill_runner = SkillRunner(brain, gateway, None)  # ReactLoop wordt hieronder gezet
    except ImportError:
        skill_selector = None
        skill_runner = None

    react_loop = ReactLoop(brain=brain, gateway=gateway, tools=tools)
    gateway.set_react_loop(react_loop)

    if skill_runner:
        skill_runner._react_loop = react_loop

    # Kill switch check
    hard = config.control_dir / "hard_stop"
    if hard.exists() and hard.read_text(encoding="utf-8").strip().lower() == "true":
        console.print("[red]Henk is gestopt. Typ /resume om te hervatten.[/red]")

    # Begroeting
    try:
        greeting = gateway.get_greeting()
        console.print(f"[cyan]{greeting}[/cyan]\n")
    except Exception:
        console.print("[cyan]Hoi. Wat kan ik voor je doen?[/cyan]\n")

    # Prompt session met autocomplete
    session = PromptSession(
        completer=_build_completer(),
        style=PROMPT_STYLE,
        complete_while_typing=False,    # Alleen autocomplete na Tab of bij /
    )

    # Context voor slash-command handlers
    command_context = {
        "brain": brain,
        "router": router,
        "gateway": gateway,
        "react_loop": react_loop,
    }

    # Main loop
    try:
        while True:
            try:
                user_input = session.prompt(
                    HTML("<prompt>❯ </prompt>"),
                    completer=_build_completer(),
                )
            except EOFError:
                break
            except KeyboardInterrupt:
                continue  # Ctrl+C in prompt = wis input, niet afsluiten

            stripped = user_input.strip()
            if not stripped:
                continue

            # Slash-command?
            if stripped.startswith("/"):
                result = dispatch_command(stripped, config, console, **command_context)
                if result == "exit":
                    break
                continue

            # Normaal bericht naar Henk
            try:
                response = gateway.process(stripped)
                if response:
                    console.print(f"[cyan]{response}[/cyan]\n")
            except KillSwitchActive as e:
                console.print(f"[red]Henk is gestopt ({e.switch_type}). Typ /resume om te hervatten.[/red]")
            except Exception:
                console.print("[red]Ik kan even niet bij mijn brein. Check je API key of internetverbinding.[/red]\n")

    except KeyboardInterrupt:
        pass

    # Cleanup
    if heartbeat:
        heartbeat.stop()

    # Sessie-samenvatting (v0.5)
    if staging and brain._history:
        try:
            summary = brain.summarize_session()
            if summary:
                from henk.memory.models import StagedChange, ChangeType, Provenance
                from datetime import datetime
                import uuid
                change = StagedChange(
                    id=uuid.uuid4().hex[:8],
                    change_type=ChangeType.CREATE,
                    target_item_id=None,
                    proposed_content=summary,
                    proposed_description=f"Sessie-samenvatting {datetime.now().strftime('%Y-%m-%d')}",
                    provenance=Provenance.AGENT_SUGGESTED,
                    reason="Automatische sessie-samenvatting",
                    timestamp=datetime.now(),
                )
                staging.stage_change(change)
                console.print("[dim]Sessie-samenvatting opgeslagen in staging.[/dim]")
        except Exception:
            pass

    console.print(f"\n[dim]Transcript: {transcript.file_path.name}[/dim]")
```

## Autocomplete gedrag

De autocomplete moet zo werken:

- Gebruiker typt `/` → dropdown verschijnt met alle commands + beschrijvingen
- Gebruiker typt `/st` → dropdown filtert naar `/status`, `/stop`
- Tab of Enter selecteert
- Gewone tekst (zonder `/`) triggert geen autocomplete

Dit wordt bereikt door `WordCompleter` met `sentence=True` en `meta_dict` voor de beschrijvingen. `complete_while_typing=False` voorkomt dat autocomplete bij normaal typen verschijnt — het triggert alleen bij `/`.

Let op: `complete_while_typing=False` betekent dat de gebruiker Tab moet drukken voor suggesties. Als je wilt dat suggesties automatisch verschijnen zodra `/` wordt getypt, gebruik dan een custom `Completer`:

```python
from prompt_toolkit.completion import Completer, Completion

class SlashCompleter(Completer):
    """Autocomplete die alleen triggert bij /."""

    def __init__(self, commands: dict[str, str]):
        self._commands = commands  # {"/stop": "Hard stop — alles stopt direct", ...}

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if not text.startswith("/"):
            return

        for cmd, desc in self._commands.items():
            if cmd.startswith(text):
                yield Completion(
                    cmd,
                    start_position=-len(text),
                    display_meta=desc,
                )
```

Gebruik deze `SlashCompleter` in plaats van `WordCompleter` als je automatische suggesties wilt bij `/`.

## Prompt-stijl

Het prompt-karakter: `❯` (Unicode right-pointing triangle). Dit is wat moderne CLI tools gebruiken. Als het terminal-compatibiliteitsproblemen geeft op Windows, fallback naar `>`.

```python
try:
    # Test of het Unicode karakter werkt
    "❯".encode(console.encoding or "utf-8")
    PROMPT_CHAR = "❯"
except (UnicodeEncodeError, LookupError):
    PROMPT_CHAR = ">"
```

## Migratie van bestaande chat-logica

De volledige chat-logica die nu in `cli.py` staat onder het `chat` command verhuist naar `repl.py`. De `chat` command in cli.py kan blijven als alias:

```python
@app.command(hidden=True)  # Verborgen — henk zonder argument is de primaire manier
def chat():
    """Start chat (alias — gebruik gewoon 'henk')."""
    data_dir = _ensure_initialized()
    config = load_config(data_dir)
    from henk.repl import start_repl
    start_repl(config, console)
```

## Tests

### test_commands.py

- dispatch_command(”/help”, …) print commands
- dispatch_command(”/exit”, …) returned “exit”
- dispatch_command(”/stop”, …) schrijft hard_stop en returned “exit”
- dispatch_command(”/pause”, …) schrijft graceful_stop
- dispatch_command(”/resume”, …) reset beide switches
- dispatch_command(”/onbekend”, …) toont foutmelding
- get_command_names() bevat alle verwachte commands

### test_repl.py

- Slash-commands worden herkend (begint met /)
- Lege input wordt genegeerd
- Niet-slash input wordt doorgegeven aan gateway.process()
- SlashCompleter geeft alleen suggesties bij /
- SlashCompleter filtert op getypte tekst

## Volgorde van bouwen

1. **commands.py** — alle handlers en dispatch logica
1. **repl.py** — REPL met prompt_toolkit en autocomplete
1. **cli.py aanpassen** — `invoke_without_command=True`, auto-init, verplaats chat-logica
1. **Tests**
1. **Opruimen** — verwijder dubbele logica uit cli.py die nu in commands.py en repl.py zit

## Samenvatting

Deze wijziging verandert:

1. `henk` = start direct de chat (auto-init)
1. Slash-commands in de chat met autocomplete en beschrijvingen
1. `henk stop` en `henk status` werken ook vanuit de terminal
1. prompt_toolkit voor moderne input-ervaring
1. Alle command-logica gecentreerd in commands.py
1. REPL-logica in repl.py, cli.py wordt dun

**Referenties:**

- `CLAUDE.md` — architectuurprincipes
- prompt_toolkit documentatie: https://python-prompt-toolkit.readthedocs.io/