"""Token-tracking per sessie."""

from __future__ import annotations


class TokenTracker:
    """Houdt tokengebruik bij per sessie."""

    def __init__(self):
        self._total_input: int = 0
        self._total_output: int = 0
        self._call_count: int = 0

    def add(self, input_tokens: int, output_tokens: int) -> None:
        """Registreer tokens van een API call."""
        self._total_input += input_tokens
        self._total_output += output_tokens
        self._call_count += 1

    @property
    def total(self) -> int:
        return self._total_input + self._total_output

    @property
    def total_input(self) -> int:
        return self._total_input

    @property
    def total_output(self) -> int:
        return self._total_output

    @property
    def call_count(self) -> int:
        return self._call_count

    def format(self) -> str:
        total = self.total
        if total < 1000:
            return f"{total} tokens"
        return f"{total / 1000:.1f}k tokens"
