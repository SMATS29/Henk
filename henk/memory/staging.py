"""Staging voor voorgestelde geheugenwijzigingen."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from henk.memory.models import ChangeType, MemoryItem, Provenance, StagedChange
from henk.memory.store import MemoryStore


class StagingManager:
    """Beheert staged memory wijzigingen."""

    def __init__(self, staging_dir: Path, store: MemoryStore):
        self._staging_dir = staging_dir
        self._store = store
        self._pending_dir = staging_dir / "pending"
        self._archive_dir = staging_dir / "archive"
        self._pending_dir.mkdir(parents=True, exist_ok=True)
        self._archive_dir.mkdir(parents=True, exist_ok=True)

    def stage_change(self, change: StagedChange) -> None:
        """Schrijf een voorgestelde wijziging naar staging."""
        if not change.id:
            change.id = f"change_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        if self._is_suspicious(change):
            change.suspicious = True
        payload = asdict(change)
        payload["change_type"] = change.change_type.value
        payload["provenance"] = change.provenance.value
        payload["timestamp"] = change.timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        (self._pending_dir / f"{change.id}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def list_pending(self) -> list[StagedChange]:
        """Lijst alle pending wijzigingen."""
        changes = [self._load_change(path) for path in sorted(self._pending_dir.glob("*.json"))]
        return sorted(changes, key=lambda change: change.timestamp)

    def approve(self, change_id: str) -> None:
        """Keur een wijziging goed en voer door naar actief geheugen."""
        path, change = self._find_change(change_id)
        if change.change_type == ChangeType.ARCHIVE:
            target_item = self._store.load_item(self._target_path(change))
            target_item.provenance = Provenance.APPROVED_BY_USER
            self._store.archive_item(target_item)
        else:
            target_path = self._target_path(change)
            target_id = change.target_item_id or target_path.removesuffix(".md")
            existing = None
            resolved = self._store.memory_dir / target_path
            if resolved.exists():
                existing = self._store.load_item(target_path)
            item = MemoryItem(
                id=target_id,
                path=target_path,
                title=change.proposed_title or (existing.title if existing else self._title_from_path(target_path)),
                description=change.proposed_description,
                content=change.proposed_content,
                score=existing.score if existing else self._store._initial_score,
                last_used=existing.last_used if existing else None,
                last_updated=datetime.now(timezone.utc),
                provenance=Provenance.APPROVED_BY_USER,
                tags=existing.tags if existing else [],
            )
            self._store.save_item(item)
        path.unlink(missing_ok=True)

    def reject(self, change_id: str) -> None:
        """Keur een wijziging af en verwijder uit staging."""
        path, _ = self._find_change(change_id)
        path.unlink(missing_ok=True)

    def _is_suspicious(self, change: StagedChange) -> bool:
        """Check of een wijziging verdacht is."""
        suspicious_patterns = [
            "system prompt",
            "persoonlijkheid",
            "gedragsregel",
            "geen bevestiging",
            "skip review",
            "altijd toestaan",
        ]
        searchable = " ".join([
            change.proposed_content,
            change.proposed_title or "",
            change.proposed_description or "",
        ]).lower()
        return any(pattern in searchable for pattern in suspicious_patterns)

    def _find_change(self, change_id: str) -> tuple[Path, StagedChange]:
        path = self._pending_dir / f"{change_id}.json"
        return path, self._load_change(path)

    def _load_change(self, path: Path) -> StagedChange:
        data = json.loads(path.read_text(encoding="utf-8"))
        return StagedChange(
            id=data["id"],
            change_type=ChangeType(data["change_type"]),
            target_item_id=data.get("target_item_id"),
            proposed_content=data["proposed_content"],
            proposed_description=data["proposed_description"],
            provenance=Provenance(data["provenance"]),
            reason=data["reason"],
            timestamp=datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00")),
            suspicious=bool(data.get("suspicious", False)),
            proposed_title=data.get("proposed_title", ""),
            target_path=data.get("target_path"),
        )

    def _target_path(self, change: StagedChange) -> str:
        if change.target_path:
            return change.target_path
        if change.target_item_id:
            return f"{change.target_item_id}.md"
        slug = self._slugify(change.proposed_title or "geheugen")
        return f"active/{slug}.md"

    @staticmethod
    def _slugify(value: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
        return normalized or "geheugen"

    @staticmethod
    def _title_from_path(path: str) -> str:
        stem = Path(path).stem
        return stem.replace("-", " ").title()
