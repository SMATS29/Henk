"""Tests voor relevance scoring."""

from datetime import datetime, timedelta, timezone

from henk.memory import MemoryItem, RelevanceScorer


def test_initial_score_is_50():
    item = MemoryItem(id="active/a", path="active/a.md", title="A", description="", content="")
    assert item.score == 50


def test_decay_applies_per_week():
    item = MemoryItem(
        id="active/a",
        path="active/a.md",
        title="A",
        description="",
        content="",
        score=50,
        last_updated=datetime.now(timezone.utc) - timedelta(days=15),
    )
    scorer = RelevanceScorer(decay_per_week=10)

    scorer.apply_decay([item])

    assert item.score == 30


def test_score_never_goes_negative():
    item = MemoryItem(
        id="active/a",
        path="active/a.md",
        title="A",
        description="",
        content="",
        score=5,
        last_updated=datetime.now(timezone.utc) - timedelta(days=30),
    )
    scorer = RelevanceScorer(decay_per_week=10)

    scorer.apply_decay([item])

    assert item.score == 0


def test_archive_candidates_are_found():
    items = [
        MemoryItem(id="active/laag", path="active/laag.md", title="Laag", description="", content="", score=5),
        MemoryItem(id="active/hoog", path="active/hoog.md", title="Hoog", description="", content="", score=20),
    ]
    scorer = RelevanceScorer(archive_threshold=10)

    candidates = scorer.get_archive_candidates(items)

    assert [item.id for item in candidates] == ["active/laag"]


def test_decay_with_no_timestamp_keeps_score_unchanged():
    """Items zonder timestamp worden niet verouderd — score blijft gelijk."""
    item = MemoryItem(
        id="active/a",
        path="active/a.md",
        title="A",
        description="",
        content="",
        score=50,
        last_used=None,
        last_updated=None,
    )
    scorer = RelevanceScorer(decay_per_week=10)

    scorer.apply_decay([item])

    assert item.score == 50


def test_decay_uses_last_used_over_last_updated():
    """last_used heeft voorrang op last_updated bij vervalberekening."""
    item = MemoryItem(
        id="active/a",
        path="active/a.md",
        title="A",
        description="",
        content="",
        score=50,
        last_used=datetime.now(timezone.utc) - timedelta(days=7),
        last_updated=datetime.now(timezone.utc) - timedelta(days=21),
    )
    scorer = RelevanceScorer(decay_per_week=10)

    scorer.apply_decay([item])

    # Gebaseerd op last_used (7 dagen = 1 week): 50 - 10 = 40
    assert item.score == 40


def test_mark_used_boosts_score_and_sets_timestamp():
    item = MemoryItem(
        id="active/a",
        path="active/a.md",
        title="A",
        description="",
        content="",
        score=30,
    )
    scorer = RelevanceScorer(use_boost=10)

    result = scorer.mark_used(item)

    assert result.score == 40
    assert result.last_used is not None
    assert result.last_used.tzinfo is not None
