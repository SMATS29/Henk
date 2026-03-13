import pytest

prompt_toolkit = pytest.importorskip("prompt_toolkit")
Document = prompt_toolkit.document.Document

from henk.repl import _build_completer


def test_completer_suggests_for_slash_prefix():
    completer = _build_completer()
    completions = list(completer.get_completions(Document(text="/st", cursor_position=3), None))
    texts = [item.text for item in completions]
    assert "/status" in texts
    assert "/stop" in texts


def test_completer_ignores_plain_text():
    completer = _build_completer()
    completions = list(completer.get_completions(Document(text="hallo", cursor_position=5), None))
    assert completions == []
