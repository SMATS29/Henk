"""JSONL transcript writer."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path


class TranscriptWriter:
    """Schrijft conversatie-transcripts als JSONL."""

    def __init__(self, logs_dir: Path):
        self._logs_dir = logs_dir
        self._session_id = uuid.uuid4().hex[:12]
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self._file_path = logs_dir / f"transcript_{timestamp}_{self._session_id}.jsonl"
        self._logs_dir.mkdir(parents=True, exist_ok=True)

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def file_path(self) -> Path:
        return self._file_path

    def write(self, role: str, content: str) -> None:
        """Schrijf een enkel bericht naar het transcript."""
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": self._session_id,
            "role": role,
            "content": content,
        }
        with open(self._file_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
