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
