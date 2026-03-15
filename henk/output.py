"""Output helpers voor Henk-antwoorden."""

from __future__ import annotations

from rich.console import Console
from rich.markdown import Markdown

from henk.gateway import Gateway


def _format_tokens(total: int) -> str:
    if total < 1000:
        return f"{total} tokens"
    return f"{total / 1000:.1f}k tokens"


def print_henk(console: Console, text: str, gateway: Gateway) -> None:
    """Print Henk's antwoord met Markdown en token-indicatie."""
    try:
        console.print(Markdown(text))
    except Exception:
        console.print(f"[cyan]{text}[/cyan]")

    token_text = f"sessie: {_format_tokens(gateway.session_tokens_total)}"
    console.print(f"[dim][right]{token_text}[/right][/dim]")
    console.print()
