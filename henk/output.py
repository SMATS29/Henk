"""Output helpers voor Henk-antwoorden."""

from __future__ import annotations

from rich.console import Console
from rich.markdown import Markdown

from henk.token_tracker import TokenTracker


def print_henk(console: Console, text: str, token_tracker: TokenTracker) -> None:
    """Print Henk's antwoord met Markdown en token-indicatie."""
    try:
        console.print(Markdown(text))
    except Exception:
        console.print(f"[cyan]{text}[/cyan]")

    token_text = f"sessie: {token_tracker.format()}"
    console.print(f"[dim][right]{token_text}[/right][/dim]")
    console.print()
