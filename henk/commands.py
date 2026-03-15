"""Slash-command definities en handlers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from copy import deepcopy
from pathlib import Path
from typing import Callable

from rich.console import Console

import yaml

from henk.config import Config
from henk.memory import MemoryStore, RelevanceScorer, StagingManager


@dataclass
class SlashCommand:
    """Definitie van een slash-command."""

    name: str
    description: str
    handler: str


COMMANDS: list[SlashCommand] = [
    SlashCommand("stop", "Hard stop — alles stopt direct", "handle_stop"),
    SlashCommand("pause", "Pauzeer — geen nieuwe taken", "handle_pause"),
    SlashCommand("resume", "Hervat na pause of stop", "handle_resume"),
    SlashCommand("model", "Beheer taaktypes, modellen en API keys", "handle_model"),
    SlashCommand("status", "Toon status van Henk", "handle_status"),
    SlashCommand("review", "Dagelijkse memory review", "handle_review"),
    SlashCommand("config", "Bekijk configuratie", "handle_config"),
    SlashCommand("help", "Toon beschikbare commands", "handle_help"),
    SlashCommand("exit", "Sluit Henk af", "handle_exit"),
    SlashCommand("clear", "Wis het scherm", "handle_clear"),
    SlashCommand("history", "Toon gespreksgeschiedenis", "handle_history"),
]

MODEL_PRESETS: dict[str, list[str]] = {
    "openai": ["gpt-5.2", "gpt-5-mini"],
}


def get_command_names() -> list[str]:
    return [f"/{cmd.name}" for cmd in COMMANDS]


def _repo_env_path() -> Path:
    return Path(__file__).resolve().parents[1] / ".env"


def _config_path(config: Config) -> Path:
    return config.data_dir / "henk.yaml"


def _mask_secret(value: str) -> str:
    if not value:
        return "leeg"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def _provider_env_name(config_data: dict, provider_name: str) -> str:
    return str(config_data.get("providers", {}).get(provider_name, {}).get("api_key_env", "")).strip()


def _build_model_options(config_data: dict) -> list[str]:
    options: list[str] = []
    for provider_name, models in MODEL_PRESETS.items():
        for model in models:
            options.append(f"{provider_name}/{model}")

    for role_cfg in config_data.get("roles", {}).values():
        primary = role_cfg.get("primary")
        if primary and primary not in options:
            options.append(primary)
        for fallback in role_cfg.get("fallback", []):
            if fallback and fallback not in options:
                options.append(fallback)

    return options


def _print_model_options(console: Console, options: list[str]) -> None:
    grouped: dict[str, list[tuple[int, str]]] = {}
    for index, provider_model in enumerate(options, start=1):
        provider_name, _, model_name = provider_model.partition("/")
        grouped.setdefault(provider_name, []).append((index, model_name))

    console.print("\n[bold]Beschikbare modellen:[/bold]")
    for provider_name, entries in grouped.items():
        console.print(f"  [cyan]{provider_name}[/cyan]")
        for index, model_name in entries:
            console.print(f"    {index}. {provider_name}/{model_name}")
    console.print("  Typ ook direct een aangepaste waarde als provider/model.\n")


def _resolve_model_token(token: str, options: list[str]) -> str | None:
    cleaned = token.strip()
    if not cleaned:
        return None
    if cleaned.isdigit():
        index = int(cleaned) - 1
        if 0 <= index < len(options):
            return options[index]
        return None
    if "/" in cleaned:
        return cleaned
    return None


def _read_env_file(path: Path) -> tuple[list[str], dict[str, str]]:
    if not path.exists():
        return [], {}

    lines = path.read_text(encoding="utf-8").splitlines()
    values: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value
    return lines, values


def _write_env_updates(path: Path, updates: dict[str, str]) -> None:
    lines, _ = _read_env_file(path)
    updated_lines: list[str] = []
    applied_keys: set[str] = set()

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            updated_lines.append(line)
            continue

        key, _, _ = line.partition("=")
        key = key.strip()
        if key in updates:
            updated_lines.append(f"{key}={updates[key]}")
            applied_keys.add(key)
        else:
            updated_lines.append(line)

    for key, value in updates.items():
        if key not in applied_keys:
            updated_lines.append(f"{key}={value}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(updated_lines).rstrip() + "\n", encoding="utf-8")


def _save_config_data(path: Path, config_data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(config_data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _reload_runtime_config(config: Config, router, config_data: dict, env_updates: dict[str, str]) -> None:
    config._data = config_data
    for key, value in env_updates.items():
        if value:
            os.environ[key] = value
        else:
            os.environ.pop(key, None)

    if router is not None:
        router._config = config
        router._initialize()


def _print_model_overview(console: Console, config_data: dict, env_values: dict[str, str]) -> None:
    console.print("\n[bold]Model-overzicht[/bold]\n")
    for role_name, role_cfg in config_data.get("roles", {}).items():
        primary = role_cfg.get("primary", "-")
        fallback = role_cfg.get("fallback", [])
        fallback_text = ", ".join(fallback) if fallback else "geen"
        console.print(f"  [cyan]{role_name:7s}[/cyan] primary: {primary}")
        console.print(f"          fallback: {fallback_text}")

    console.print("\n[bold]Provider-overzicht[/bold]\n")
    for provider_name, provider_cfg in config_data.get("providers", {}).items():
        env_name = str(provider_cfg.get("api_key_env", "")).strip()
        if env_name:
            value = env_values.get(env_name, os.environ.get(env_name, ""))
            console.print(f"  [cyan]{provider_name:10s}[/cyan] key: {_mask_secret(value)} ({env_name})")
        else:
            base_url = provider_cfg.get("base_url", "-")
            console.print(f"  [cyan]{provider_name:10s}[/cyan] lokaal: {base_url}")
    console.print()


def _edit_role_models(
    console: Console,
    config_data: dict,
    input_func: Callable[[str], str],
) -> None:
    roles = list(config_data.get("roles", {}).keys())
    if not roles:
        console.print("[red]Geen rollen gevonden in configuratie.[/red]")
        return

    console.print("\n[bold]Kies een taaktype:[/bold]")
    for index, role_name in enumerate(roles, start=1):
        console.print(f"  {index}. {role_name}")
    choice = input_func("Rolnummer (leeg = terug): ").strip()
    if not choice:
        return
    if not choice.isdigit() or not (1 <= int(choice) <= len(roles)):
        console.print("[red]Ongeldige rolkeuze.[/red]")
        return

    role_name = roles[int(choice) - 1]
    role_cfg = config_data.setdefault("roles", {}).setdefault(role_name, {})
    options = _build_model_options(config_data)
    _print_model_options(console, options)

    primary_raw = input_func(f"Primary voor {role_name} [{role_cfg.get('primary', '')}]: ").strip()
    if primary_raw:
        primary = _resolve_model_token(primary_raw, options)
        if not primary:
            console.print("[red]Ongeldige primary-keuze.[/red]")
            return
        role_cfg["primary"] = primary

    current_fallback = ", ".join(role_cfg.get("fallback", []))
    fallback_raw = input_func(f"Fallbacks voor {role_name} [{current_fallback or 'geen'}]: ").strip()
    if fallback_raw:
        fallback_values: list[str] = []
        for token in fallback_raw.split(","):
            resolved = _resolve_model_token(token, options)
            if not resolved:
                console.print(f"[red]Ongeldige fallback-keuze: {token.strip()}[/red]")
                return
            if resolved != role_cfg.get("primary") and resolved not in fallback_values:
                fallback_values.append(resolved)
        role_cfg["fallback"] = fallback_values

    console.print(f"[green]Rol '{role_name}' bijgewerkt.[/green]")


def _edit_provider_key(
    console: Console,
    config_data: dict,
    env_values: dict[str, str],
    input_func: Callable[[str], str],
) -> dict[str, str]:
    providers = [
        provider_name
        for provider_name, provider_cfg in config_data.get("providers", {}).items()
        if provider_cfg.get("api_key_env")
    ]
    if not providers:
        console.print("[red]Geen providers met API keys gevonden.[/red]")
        return {}

    console.print("\n[bold]Kies een provider:[/bold]")
    for index, provider_name in enumerate(providers, start=1):
        env_name = _provider_env_name(config_data, provider_name)
        console.print(f"  {index}. {provider_name} ({env_name})")
    choice = input_func("Providernummer (leeg = terug): ").strip()
    if not choice:
        return {}
    if not choice.isdigit() or not (1 <= int(choice) <= len(providers)):
        console.print("[red]Ongeldige provider-keuze.[/red]")
        return {}

    provider_name = providers[int(choice) - 1]
    env_name = _provider_env_name(config_data, provider_name)
    current_value = env_values.get(env_name, os.environ.get(env_name, ""))
    console.print(f"Huidige waarde: {_mask_secret(current_value)}")
    console.print("[dim]Leeg laten = behouden, '-' = wissen[/dim]")
    new_value = input_func(f"Nieuwe {env_name}: ")

    if new_value == "":
        return {}
    if new_value.strip() == "-":
        console.print(f"[yellow]{env_name} wordt gewist.[/yellow]")
        return {env_name: ""}

    console.print(f"[green]{env_name} bijgewerkt.[/green]")
    return {env_name: new_value.strip()}


def _read_switch(config: Config, name: str) -> bool:
    path = config.control_dir / name
    if path.exists():
        return path.read_text(encoding="utf-8").strip().lower() == "true"
    return False


def handle_stop(config: Config, console: Console, **kwargs) -> str | None:
    (config.control_dir / "hard_stop").write_text("true", encoding="utf-8")
    console.print("[red]Henk is gestopt.[/red]")
    return "exit"


def handle_pause(config: Config, console: Console, **kwargs) -> str | None:
    (config.control_dir / "graceful_stop").write_text("true", encoding="utf-8")
    console.print("[yellow]Henk is gepauzeerd. Geen nieuwe taken.[/yellow]")
    return None


def handle_resume(config: Config, console: Console, **kwargs) -> str | None:
    (config.control_dir / "graceful_stop").write_text("false", encoding="utf-8")
    (config.control_dir / "hard_stop").write_text("false", encoding="utf-8")
    console.print("[green]Henk is hervat.[/green]")
    return None


def handle_status(config: Config, console: Console, **kwargs) -> str | None:
    hard = _read_switch(config, "hard_stop")
    graceful = _read_switch(config, "graceful_stop")
    if hard:
        state = "[red]gestopt[/red]"
    elif graceful:
        state = "[yellow]gepauzeerd[/yellow]"
    else:
        state = "[green]normaal[/green]"

    file_count = sum(1 for _ in config.workspace_dir.rglob("*")) if config.workspace_dir.exists() else 0

    latest_log = "geen"
    if config.logs_dir.exists():
        logs = sorted(config.logs_dir.glob("transcript_*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        if logs:
            latest_log = logs[0].name

    console.print(f"  Kill switch:  {state}")
    console.print(f"  Workspace:    {file_count} bestanden")
    console.print(f"  Laatste log:  {latest_log}")
    return None


def handle_review(config: Config, console: Console, **kwargs) -> str | None:
    store = MemoryStore(config.memory_dir, initial_score=config.memory_scoring["initial_score"])
    staging = StagingManager(config.memory_dir / ".staged", store)
    scorer = RelevanceScorer(**config.memory_scoring)

    pending = staging.list_pending()
    if not pending:
        console.print("[dim]Geen openstaande geheugenwijzigingen.[/dim]")
        return None

    import typer

    console.print(f"\n[bold]{len(pending)} wijziging(en) wachten op review:[/bold]\n")
    for change in pending:
        if change.suspicious:
            console.print("  [red]⚠ VERDACHT[/red]")
        console.print(f"  Type:     {change.change_type.value}")
        console.print(f"  Herkomst: {change.provenance.value}")
        console.print(f"  Reden:    {change.reason}")
        console.print(f"  Inhoud:   {change.proposed_content[:200]}...")

        if typer.confirm("  Goedkeuren?", default=not change.suspicious):
            staging.approve(change.id)
            console.print("  [green]✓ Goedgekeurd[/green]\n")
        else:
            staging.reject(change.id)
            console.print("  [red]✗ Afgewezen[/red]\n")

    active_items = store.list_items("active") + store.list_items("episodes")
    original_scores = {item.id: item.score for item in active_items}
    scorer.apply_decay(active_items)
    for item in active_items:
        if item.score != original_scores[item.id]:
            store.save_item(item)

    console.print("[dim]Review afgerond.[/dim]")
    return None


def handle_config(config: Config, console: Console, **kwargs) -> str | None:
    console.print(f"  Max tool-calls:        {config.max_tool_calls}")
    console.print(f"  Max retries (content): {config.max_retries_content}")
    console.print(f"  Max retries (tech):    {config.max_retries_technical}")
    console.print(f"  Data dir:              {config.data_dir}")
    return None


def handle_model(config: Config, console: Console, **kwargs) -> str | None:
    input_func = kwargs.get("input_func", input)
    router = kwargs.get("router")
    env_path = Path(kwargs.get("env_path", _repo_env_path()))
    config_path = Path(kwargs.get("config_path", _config_path(config)))

    config_data = deepcopy(config.raw)
    _, env_values = _read_env_file(env_path)
    pending_env_updates: dict[str, str] = {}

    while True:
        _print_model_overview(console, config_data, {**env_values, **pending_env_updates})
        console.print("  1. Taaktype en modellen aanpassen")
        console.print("  2. API keys aanpassen")
        console.print("  0. Opslaan en sluiten")
        console.print("  9. Annuleren\n")

        choice = input_func("Kies een optie [0]: ").strip() or "0"
        if choice == "1":
            _edit_role_models(console, config_data, input_func)
            continue
        if choice == "2":
            updates = _edit_provider_key(console, config_data, {**env_values, **pending_env_updates}, input_func)
            pending_env_updates.update(updates)
            continue
        if choice == "9":
            console.print("[dim]Wijzigingen geannuleerd.[/dim]")
            return None
        if choice != "0":
            console.print("[red]Ongeldige keuze.[/red]")
            continue

        _save_config_data(config_path, config_data)
        if pending_env_updates:
            _write_env_updates(env_path, pending_env_updates)
        _reload_runtime_config(config, router, config_data, pending_env_updates)
        console.print(f"[green]Modelconfiguratie opgeslagen in {config_path.name} en {env_path.name}.[/green]")
        return None


def handle_help(config: Config, console: Console, **kwargs) -> str | None:
    console.print("\n[bold]Beschikbare commands:[/bold]\n")
    for cmd in COMMANDS:
        console.print(f"  [cyan]/{cmd.name:10s}[/cyan] {cmd.description}")
    if kwargs.get("shift_enter_supported"):
        console.print("\n[dim]Invoer: Shift+Enter maakt een nieuwe regel; Tab accepteert een slash-suggestie.[/dim]")
    else:
        console.print("\n[dim]Je terminal geeft Shift+Enter hier niet apart door; multiline invoer is daardoor beperkt.[/dim]")
        console.print("[dim]Tab accepteert een slash-suggestie zoals /clear of /config.[/dim]")
    console.print()
    return None


def handle_exit(config: Config, console: Console, **kwargs) -> str | None:
    return "exit"


def handle_clear(config: Config, console: Console, **kwargs) -> str | None:
    console.clear()
    return None


def handle_history(config: Config, console: Console, **kwargs) -> str | None:
    brain = kwargs.get("brain")
    if not brain or not brain.has_history:
        console.print("[dim]Nog geen gesprek in deze sessie.[/dim]")
        return None

    console.print("\n[bold]Gespreksgeschiedenis:[/bold]\n")
    for message in brain._history:
        role = message.get("role", "?")
        content = message.get("content", "")
        if role == "user":
            console.print(f"  [bold]Jij:[/bold] {str(content)[:150]}")
        else:
            console.print(f"  [cyan]Henk:[/cyan] {str(content)[:150]}")
    console.print()
    return None


def dispatch_command(command: str, config: Config, console: Console, **kwargs) -> str | None:
    cmd_name = command.lstrip("/").strip().split()[0].lower()
    handlers = {
        "stop": handle_stop,
        "pause": handle_pause,
        "resume": handle_resume,
        "model": handle_model,
        "status": handle_status,
        "review": handle_review,
        "config": handle_config,
        "help": handle_help,
        "exit": handle_exit,
        "clear": handle_clear,
        "history": handle_history,
    }
    handler = handlers.get(cmd_name)
    if not handler:
        console.print(f"[red]Onbekend command: /{cmd_name}[/red] — typ /help voor opties.")
        return None
    return handler(config, console, **kwargs)
