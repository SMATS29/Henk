"""Tests voor de TranscriptWriter."""

import json

from henk.transcript import TranscriptWriter


def test_transcript_writes_valid_jsonl(tmp_path):
    """Transcript schrijft geldige JSONL."""
    writer = TranscriptWriter(tmp_path / "logs")

    writer.write("user", "hallo")
    writer.write("assistant", "hoi!")

    lines = writer.file_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2

    record1 = json.loads(lines[0])
    assert record1["role"] == "user"
    assert record1["content"] == "hallo"
    assert "timestamp" in record1
    assert record1["session_id"] == writer.session_id

    record2 = json.loads(lines[1])
    assert record2["role"] == "assistant"
    assert record2["content"] == "hoi!"


def test_transcript_creates_log_dir(tmp_path):
    """Transcript maakt de logs directory aan als die niet bestaat."""
    log_dir = tmp_path / "does" / "not" / "exist"
    writer = TranscriptWriter(log_dir)
    writer.write("user", "test")
    assert log_dir.exists()
    assert writer.file_path.exists()
