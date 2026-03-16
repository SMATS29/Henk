"""Taakpaneel en statusbalk tijdens verwerking."""

from __future__ import annotations

from datetime import datetime

from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.text import Text

from henk.gateway import Gateway, RunStatus, TaskInfo


def _format_time(seconds: float) -> str:
    """Formatteer seconden als m:ss."""
    minutes = int(seconds) // 60
    secs = int(seconds) % 60
    return f"{minutes}:{secs:02d}"


def _format_tokens(total: int) -> str:
    """Formatteer tokentelling."""
    if total < 1000:
        return f"{total} tokens"
    return f"{total / 1000:.1f}k tokens"


def _build_task_table(tasks: list[TaskInfo]) -> Table:
    """Bouw de task-panel tabel."""
    table = Table(show_header=False, show_edge=False, pad_edge=False, box=None, expand=True)
    table.add_column("icon", width=2, no_wrap=True)
    table.add_column("summary", ratio=1, no_wrap=True)
    table.add_column("time", width=6, justify="right", no_wrap=True)
    table.add_column("tokens", width=14, justify="right", no_wrap=True)

    active = [t for t in tasks if t.status == RunStatus.ACTIVE]
    completed = [t for t in tasks if t.status != RunStatus.ACTIVE]
    completed.sort(key=lambda t: t.started_at, reverse=True)
    ordered = active + completed

    now = datetime.now()
    for task in ordered[:5]:
        if task.status == RunStatus.ACTIVE:
            icon = Text("\u25cf", style="bold green")
            elapsed = (now - task.started_at).total_seconds()
        elif task.status == RunStatus.DONE:
            icon = Text("\u2713", style="dim")
            elapsed = (task.ended_at - task.started_at).total_seconds() if task.ended_at else 0
        else:
            icon = Text("\u2717", style="bold red")
            elapsed = (task.ended_at - task.started_at).total_seconds() if task.ended_at else 0

        summary = task.summary[:40] + ("\u2026" if len(task.summary) > 40 else "")
        style = "dim" if task.status != RunStatus.ACTIVE else ""
        total_tokens = task.tokens_input + task.tokens_output

        table.add_row(
            icon,
            Text(summary, style=style),
            Text(_format_time(elapsed), style=style),
            Text(_format_tokens(total_tokens), style=style),
        )

    return table


def _build_status_bar(gateway: Gateway) -> Text:
    """Bouw de sessie-statusregel."""
    total = gateway.session_tokens_total
    inp = gateway.session_tokens_input
    out = gateway.session_tokens_output
    inp_str = _format_tokens(inp).replace(" tokens", "")
    out_str = _format_tokens(out).replace(" tokens", "")
    return Text(f"Sessie: {_format_tokens(total)}  ({inp_str} in \u00b7 {out_str} uit)", style="dim")


class TaskDisplay:
    """Beheert het taakpaneel en de statusbalk tijdens verwerking."""

    def __init__(self, console: Console, gateway: Gateway):
        self._console = console
        self._gateway = gateway
        self._live: Live | None = None
        self._status_message: str = ""

    def _render(self) -> Table:
        """Render het volledige display: taakpaneel + statusbalk."""
        outer = Table(show_header=False, show_edge=False, box=None, expand=True, pad_edge=False)
        outer.add_column(ratio=1)

        if self._status_message:
            outer.add_row(Text(f"\u28cb {self._status_message}", style="bold cyan"))

        tasks = self._gateway.get_task_state()
        if tasks:
            outer.add_row(_build_task_table(tasks))

        outer.add_row(_build_status_bar(self._gateway))

        return outer

    def open_session(self) -> None:
        """Start de persistent Live context voor de hele REPL-sessie."""
        if self._live is not None:
            return
        self._live = Live(
            self._render(),
            console=self._console,
            refresh_per_second=1,
            transient=False,
            vertical_overflow="visible",
        )
        self._live.start()

    def close_session(self) -> None:
        """Stop de persistent Live context bij afsluiten van de REPL."""
        if self._live is not None:
            self._live.stop()
            self._live = None
        self._status_message = ""

    def start(self, message: str = "Henk denkt...") -> None:
        """Start het live display (backwards-compatible)."""
        self._status_message = message
        if self._live is not None:
            self._live.update(self._render())
            return
        self._live = Live(
            self._render(),
            console=self._console,
            refresh_per_second=1,
            transient=True,
        )
        self._live.start()

    def update(self, message: str) -> None:
        """Update het spinner-bericht en herrender."""
        self._status_message = message
        if self._live is not None:
            self._live.update(self._render())

    def update_task(self, message: str) -> None:
        """Update het taakpaneel."""
        self.update(message)

    def stop(self) -> None:
        """Stop het live display (backwards-compatible, sluit geen sessie)."""
        if self._live is not None:
            self._live.stop()
            self._live = None
        self._status_message = ""

    def print_static_panel(self) -> None:
        """Print een statisch snapshot van het taakpaneel."""
        tasks = self._gateway.get_task_state()
        if tasks:
            self._console.print(_build_task_table(tasks))
