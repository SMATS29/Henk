"""CRUD op geheugenbestanden met YAML frontmatter."""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from henk.memory.models import MemoryItem, Provenance

try:
    import frontmatter
except ImportError:  # pragma: no cover - fallback voor minimale testomgeving
    frontmatter = None


class MemoryStore:
    """Beheert memory-items op schijf."""

    def __init__(self, memory_dir: Path, initial_score: int = 50):
        self._memory_dir = memory_dir.expanduser().resolve()
        self._initial_score = initial_score
        (self._memory_dir / "active").mkdir(parents=True, exist_ok=True)
        (self._memory_dir / "episodes").mkdir(parents=True, exist_ok=True)
        (self._memory_dir / ".staged" / "archive").mkdir(parents=True, exist_ok=True)

    @property
    def memory_dir(self) -> Path:
        return self._memory_dir

    def load_item(self, path: str | Path) -> MemoryItem:
        """Laad een memory-item van schijf."""
        resolved = self._resolve_path(path)
        text = resolved.read_text(encoding="utf-8")
        metadata, content = self._parse_document(text)
        rel_path = resolved.relative_to(self._memory_dir).as_posix()
        return MemoryItem(
            id=str(metadata.get("id") or rel_path.removesuffix(".md")),
            path=rel_path,
            title=str(metadata.get("title") or self._title_from_content(content, resolved.stem)),
            description=str(metadata.get("description") or ""),
            content=content.strip(),
            score=int(metadata.get("score", self._initial_score)),
            last_used=self._parse_datetime(metadata.get("last_used")),
            last_updated=self._parse_datetime(metadata.get("last_updated")),
            provenance=Provenance(str(metadata.get("provenance", Provenance.USER_AUTHORED.value))),
            tags=list(metadata.get("tags") or []),
        )

    def save_item(self, item: MemoryItem) -> None:
        """Schrijf een memory-item met frontmatter weg."""
        resolved = self._resolve_path(item.path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        if item.last_updated is None:
            item.last_updated = datetime.now(timezone.utc)
        metadata = {
            "id": item.id,
            "title": item.title,
            "description": item.description,
            "score": item.score,
            "last_used": self._format_datetime(item.last_used),
            "last_updated": self._format_datetime(item.last_updated),
            "provenance": item.provenance.value,
            "tags": item.tags,
        }
        resolved.write_text(self._render_document(metadata, item.content.strip()), encoding="utf-8")

    def list_items(self, layer: str) -> list[MemoryItem]:
        """Lijst alle items in core/active/episodes."""
        if layer == "core":
            core_path = self._memory_dir / "core.md"
            return [self.load_item(core_path)] if core_path.exists() else []
        layer_path = self._memory_dir / layer
        if not layer_path.exists():
            return []
        return [self.load_item(path) for path in sorted(layer_path.rglob("*.md")) if path.is_file()]

    def archive_item(self, item: MemoryItem) -> None:
        """Verplaats een item naar de staging-archive map."""
        source = self._resolve_path(item.path)
        target = self._memory_dir / ".staged" / "archive" / item.path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))

    def load_core(self) -> str:
        """Laad core.md als plain text."""
        core_path = self._memory_dir / "core.md"
        if not core_path.exists():
            return ""
        return core_path.read_text(encoding="utf-8").strip()

    def _resolve_path(self, path: str | Path) -> Path:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self._memory_dir / candidate
        return candidate.expanduser().resolve()

    def _parse_document(self, text: str) -> tuple[dict[str, Any], str]:
        if frontmatter is not None:
            post = frontmatter.loads(text)
            return dict(post.metadata), str(post.content)
        if text.startswith("---\n"):
            _, raw_metadata, content = text.split("---\n", 2)
            return yaml.safe_load(raw_metadata) or {}, content
        return {}, text

    def _render_document(self, metadata: dict[str, Any], content: str) -> str:
        clean_metadata = {key: value for key, value in metadata.items() if value not in (None, "", [])}
        if frontmatter is not None:
            post = frontmatter.Post(content, **clean_metadata)
            return frontmatter.dumps(post)
        frontmatter_block = yaml.safe_dump(clean_metadata, allow_unicode=False, sort_keys=False).strip()
        return f"---\n{frontmatter_block}\n---\n\n{content}\n"

    @staticmethod
    def _format_datetime(value: datetime | None) -> str | None:
        if value is None:
            return None
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))

    @staticmethod
    def _title_from_content(content: str, fallback: str) -> str:
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                return stripped.lstrip("# ")
        return fallback.replace("-", " ").title()
