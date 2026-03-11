"""Gateway: validatie, limieten, logging."""

from __future__ import annotations

from pathlib import Path

from henk.brain import Brain
from henk.config import Config
from henk.transcript import TranscriptWriter


class KillSwitchActive(Exception):
    """Raised wanneer een kill switch actief is."""

    def __init__(self, switch_type: str):
        self.switch_type = switch_type
        super().__init__(f"Kill switch actief: {switch_type}")


class Gateway:
    """Bewaakt limieten, valideert berichten, logt alles."""

    def __init__(self, config: Config, brain: Brain, transcript: TranscriptWriter):
        self._config = config
        self._brain = brain
        self._transcript = transcript
        self._tool_call_count = 0

    @property
    def tool_call_count(self) -> int:
        return self._tool_call_count

    def check_kill_switches(self) -> str | None:
        """Check kill switches. Geeft het type terug als actief, anders None."""
        control_dir = self._config.control_dir

        hard_stop = control_dir / "hard_stop"
        if hard_stop.exists() and hard_stop.read_text(encoding="utf-8").strip().lower() == "true":
            return "hard_stop"

        graceful_stop = control_dir / "graceful_stop"
        if graceful_stop.exists() and graceful_stop.read_text(encoding="utf-8").strip().lower() == "true":
            return "graceful_stop"

        return None

    def process(self, user_message: str) -> str:
        """Verwerk een gebruikersbericht via de Brain."""
        # Check kill switches
        active_switch = self.check_kill_switches()
        if active_switch:
            raise KillSwitchActive(active_switch)

        # Validatie
        if not user_message or not user_message.strip():
            return ""

        # Log inkomend bericht
        self._transcript.write("user", user_message)

        # Stuur naar Brain
        response = self._brain.think(user_message)

        # Log antwoord
        self._transcript.write("assistant", response)

        return response

    def get_greeting(self) -> str:
        """Haal een begroeting op via de Brain."""
        greeting = self._brain.greet()
        self._transcript.write("assistant", greeting)
        return greeting
