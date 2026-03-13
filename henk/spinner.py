"""Visuele feedback tijdens verwerking."""

from __future__ import annotations

from rich.console import Console


class Spinner:
    """Beheert de spinner-indicator in de REPL."""

    def __init__(self, console: Console):
        self._console = console
        self._status = None

    def start(self, message: str = "Henk denkt...") -> None:
        """Start of update de spinner met een nieuw bericht."""
        if self._status is not None:
            self._status.update(message)
            return

        self._status = self._console.status(message, spinner="dots")
        self._status.start()

    def update(self, message: str) -> None:
        """Update het spinner-bericht."""
        if self._status is not None:
            self._status.update(message)

    def stop(self) -> None:
        """Stop de spinner."""
        if self._status is not None:
            self._status.stop()
            self._status = None
