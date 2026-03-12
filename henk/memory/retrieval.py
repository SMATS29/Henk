"""Memory retrieval via core.md en vector/lexicale search."""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

from henk.memory.models import MemoryItem
from henk.memory.scoring import RelevanceScorer
from henk.memory.store import MemoryStore

try:
    import chromadb
except ImportError:  # pragma: no cover - fallback voor minimale testomgeving
    chromadb = None


class MemoryRetrieval:
    """Haalt relevante geheugencontext op voor LLM-calls."""

    def __init__(
        self,
        memory_dir: Path,
        store: MemoryStore,
        scorer: RelevanceScorer,
        *,
        vector_enabled: bool = True,
        relevance_threshold: float = 0.3,
    ):
        self._memory_dir = memory_dir
        self._store = store
        self._scorer = scorer
        self._vector_enabled = vector_enabled
        self._relevance_threshold = relevance_threshold
        self._collection = self._init_collection() if vector_enabled else None

    def get_context(self, query: str) -> str:
        """Bouw context op uit core.md en relevante geheugenitems."""
        parts: list[str] = []
        core = self._store.load_core()
        if core:
            parts.append(core)

        items = self._store.list_items("active") + self._store.list_items("episodes")
        if not items:
            return "\n\n".join(parts).strip()

        original_scores = {item.id: item.score for item in items}
        self._scorer.apply_decay(items)
        for item in items:
            if item.score != original_scores[item.id]:
                self._store.save_item(item)

        self.rebuild_index(items)
        relevant_items = self._search(query, items)
        for item in relevant_items:
            self._scorer.mark_used(item)
            self._store.save_item(item)
            parts.append(f"## {item.title}\n{item.content}")

        return "\n\n".join(part for part in parts if part).strip()

    def rebuild_index(self, items: list[MemoryItem] | None = None) -> None:
        """Herbouw de vector index vanaf alle geheugenbestanden."""
        if self._collection is None:
            return
        memory_items = items or (self._store.list_items("active") + self._store.list_items("episodes"))
        existing = self._collection.get()
        ids = existing.get("ids", []) if isinstance(existing, dict) else []
        if ids:
            self._collection.delete(ids=ids)
        if not memory_items:
            return
        self._collection.add(
            ids=[item.id for item in memory_items],
            documents=[item.description or item.title for item in memory_items],
            metadatas=[{"path": item.path, "score": item.score} for item in memory_items],
        )

    def _init_collection(self):
        if chromadb is None:
            return None
        client = chromadb.PersistentClient(path=str(self._memory_dir / ".vectordb"))
        return client.get_or_create_collection(
            name="henk_memory",
            metadata={"hnsw:space": "cosine"},
        )

    def _search(self, query: str, items: list[MemoryItem]) -> list[MemoryItem]:
        if not query.strip() or not items:
            return []
        item_map = {item.id: item for item in items}
        if self._collection is not None:
            result = self._collection.query(
                query_texts=[query],
                n_results=min(5, len(items)),
                include=["distances"],
            )
            ids = result.get("ids", [[]])[0]
            distances = result.get("distances", [[]])[0]
            matches = []
            for item_id, distance in zip(ids, distances):
                similarity = max(0.0, 1.0 - float(distance))
                item = item_map.get(item_id)
                if item is not None and similarity >= self._relevance_threshold:
                    matches.append((similarity, item))
            return [item for _, item in sorted(matches, key=lambda pair: pair[0], reverse=True)]

        matches = []
        query_tokens = self._tokens(query)
        for item in items:
            haystack_tokens = self._tokens(f"{item.title} {item.description} {item.content}")
            if not haystack_tokens:
                continue
            overlap = len(query_tokens & haystack_tokens)
            norm = math.sqrt(len(query_tokens) * len(haystack_tokens))
            similarity = overlap / norm if norm else 0.0
            if similarity >= self._relevance_threshold:
                matches.append((similarity, item))
        return [item for _, item in sorted(matches, key=lambda pair: pair[0], reverse=True)]

    @staticmethod
    def _tokens(value: str) -> set[str]:
        return {token for token in re.findall(r"[a-z0-9]+", value.lower()) if token}
