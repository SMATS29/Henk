from pathlib import Path

import pytest

from henk.skills.parser import SkillParser


def test_parser_parses_valid_skill(tmp_path: Path):
    content = """---
name: demo
summary: test
tags: [x]
tools_required: [file_manager]
---

## Stap 1: Start
Tekst

**Actie:** Doe iets
**Output:** Iets
"""
    path = tmp_path / "demo.md"
    path.write_text(content, encoding="utf-8")

    skill = SkillParser().parse(path)
    assert skill.name == "demo"
    assert skill.steps[0].number == 1
    assert skill.steps[0].action == "Doe iets"


def test_parser_missing_action_output_graceful(tmp_path: Path):
    path = tmp_path / "demo.md"
    path.write_text(
        "---\nname: demo\nsummary: test\n---\n\n## Stap 1: Start\nAlleen instructie\n",
        encoding="utf-8",
    )
    skill = SkillParser().parse(path)
    assert "Alleen instructie" in skill.steps[0].action
    assert skill.steps[0].expected_output == ""


def test_parser_raises_on_invalid_file(tmp_path: Path):
    path = tmp_path / "bad.md"
    path.write_text("---\nsummary: x\n---\ngeen stappen", encoding="utf-8")
    with pytest.raises(ValueError):
        SkillParser().parse(path)
