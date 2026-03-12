"""Tests voor MemoryStore."""

from datetime import datetime, timezone

from henk.memory import MemoryItem, MemoryStore, Provenance


def test_save_and_load_item_with_frontmatter(tmp_path):
    store = MemoryStore(tmp_path)
    item = MemoryItem(
        id="active/project-henk",
        path="active/project-henk.md",
        title="Project Henk",
        description="Architectuur en voortgang.",
        content="# Project Henk\n\nBelangrijke context.",
        score=65,
        last_used=datetime(2026, 3, 12, 14, 30, tzinfo=timezone.utc),
        last_updated=datetime(2026, 3, 12, 10, 0, tzinfo=timezone.utc),
        provenance=Provenance.APPROVED_BY_USER,
        tags=["project", "architectuur"],
    )

    store.save_item(item)
    loaded = store.load_item("active/project-henk.md")

    assert loaded.id == item.id
    assert loaded.title == item.title
    assert loaded.description == item.description
    assert loaded.score == 65
    assert loaded.provenance == Provenance.APPROVED_BY_USER
    assert loaded.tags == ["project", "architectuur"]


def test_list_items_returns_items_for_layer(tmp_path):
    store = MemoryStore(tmp_path)
    store.save_item(MemoryItem(id="active/a", path="active/a.md", title="A", description="A", content="A"))
    store.save_item(MemoryItem(id="episodes/b", path="episodes/b.md", title="B", description="B", content="B"))

    active_items = store.list_items("active")
    episode_items = store.list_items("episodes")

    assert [item.id for item in active_items] == ["active/a"]
    assert [item.id for item in episode_items] == ["episodes/b"]


def test_archive_item_moves_file_to_archive(tmp_path):
    store = MemoryStore(tmp_path)
    item = MemoryItem(id="active/archive-me", path="active/archive-me.md", title="Archive", description="", content="x")
    store.save_item(item)

    store.archive_item(item)

    assert not (tmp_path / "active" / "archive-me.md").exists()
    assert (tmp_path / ".staged" / "archive" / "active" / "archive-me.md").exists()


def test_load_core_returns_raw_content(tmp_path):
    store = MemoryStore(tmp_path)
    (tmp_path / "core.md").write_text("# Kern\n\nAltijd mee", encoding="utf-8")

    assert store.load_core() == "# Kern\n\nAltijd mee"
