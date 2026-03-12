"""Relevantie-scoring voor geheugenitems."""

from __future__ import annotations

from datetime import datetime, timezone

from henk.memory.models import MemoryItem


class RelevanceScorer:
    """Past verval, gebruiksboost en archiveringsselectie toe."""

    def __init__(
        self,
        initial_score: int = 50,
        decay_per_week: int = 10,
        use_boost: int = 10,
        archive_threshold: int = 10,
    ):
        self.initial_score = initial_score
        self.decay_per_week = decay_per_week
        self.use_boost = use_boost
        self.archive_threshold = archive_threshold

    def apply_decay(self, items: list[MemoryItem]) -> list[MemoryItem]:
        """Pas weekverval toe vanaf laatste gebruik of update."""
        now = datetime.now(timezone.utc)
        for item in items:
            reference = item.last_used or item.last_updated
            if reference is None:
                item.score = max(0, item.score)
                continue
            elapsed_days = max(0, (now - reference.astimezone(timezone.utc)).days)
            weeks = elapsed_days // 7
            item.score = max(0, item.score - weeks * self.decay_per_week)
        return items

    def mark_used(self, item: MemoryItem) -> MemoryItem:
        """Verhoog score nadat het item echt in context zat."""
        item.score = max(0, item.score) + self.use_boost
        item.last_used = datetime.now(timezone.utc)
        return item

    def get_archive_candidates(self, items: list[MemoryItem]) -> list[MemoryItem]:
        """Vind items onder de archiveringsdrempel."""
        return [item for item in items if item.score < self.archive_threshold]
