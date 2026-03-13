from pathlib import Path

from henk.router.providers.base import ProviderResponse
from henk.skills.selector import SkillSelector


class DummyProvider:
    def __init__(self, text: str):
        self._text = text

    def chat(self, **kwargs):
        return ProviderResponse(text=self._text, tool_calls=None, raw=None)


class DummyRouter:
    def __init__(self, text: str):
        self._provider = DummyProvider(text)

    def get_provider(self, *args, **kwargs):
        return self._provider


def _write_skill(path: Path, name: str, summary: str):
    path.write_text(
        f"---\nname: {name}\nsummary: {summary}\n---\n\n## Stap 1: Start\nX\n",
        encoding="utf-8",
    )


def test_selector_selects_matching_skill(tmp_path: Path):
    _write_skill(tmp_path / "a.md", "schrijf", "Schrijven")
    selector = SkillSelector(tmp_path, DummyRouter("schrijf"))
    skill = selector.select("Schrijf iets")
    assert skill is not None
    assert skill.name == "schrijf"


def test_selector_returns_none_for_geen(tmp_path: Path):
    _write_skill(tmp_path / "a.md", "schrijf", "Schrijven")
    selector = SkillSelector(tmp_path, DummyRouter("geen"))
    assert selector.select("Hoi") is None


def test_selector_empty_dir_returns_none(tmp_path: Path):
    selector = SkillSelector(tmp_path / "missing", DummyRouter("x"))
    assert selector.select("test") is None
