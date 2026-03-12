"""Tests voor memory retrieval."""

from datetime import datetime, timezone

from henk.memory import MemoryItem, MemoryRetrieval, MemoryStore, RelevanceScorer


def test_core_is_always_included_in_context(tmp_path):
    store = MemoryStore(tmp_path)
    (tmp_path / "core.md").write_text("# Kern\n\nAltijd mee", encoding="utf-8")
    retrieval = MemoryRetrieval(tmp_path, store, RelevanceScorer(), vector_enabled=False)

    context = retrieval.get_context("onverwante vraag")

    assert "Altijd mee" in context


def test_retrieval_finds_relevant_items_and_boosts_score(tmp_path):
    store = MemoryStore(tmp_path)
    store.save_item(
        MemoryItem(
            id="active/project-henk",
            path="active/project-henk.md",
            title="Project Henk",
            description="Voortgang van het Henk project en architectuur.",
            content="Belangrijke voortgang.",
            score=50,
            last_updated=datetime(2026, 3, 12, tzinfo=timezone.utc),
        )
    )
    retrieval = MemoryRetrieval(tmp_path, store, RelevanceScorer(use_boost=10), vector_enabled=False, relevance_threshold=0.2)

    context = retrieval.get_context("Wat is de voortgang van Henk?")
    updated = store.load_item("active/project-henk.md")

    assert "Belangrijke voortgang." in context
    assert updated.score == 60
    assert updated.last_used is not None


def test_items_below_threshold_are_not_included(tmp_path):
    store = MemoryStore(tmp_path)
    store.save_item(MemoryItem(id="active/voetbal", path="active/voetbal.md", title="Voetbal", description="Wedstrijden", content="Uitslagen"))
    retrieval = MemoryRetrieval(tmp_path, store, RelevanceScorer(), vector_enabled=False, relevance_threshold=0.8)

    context = retrieval.get_context("project architectuur")

    assert "Uitslagen" not in context
