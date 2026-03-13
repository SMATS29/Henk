from unittest.mock import MagicMock

from henk.requirements import Requirements
from henk.skills.models import Skill, SkillStep, StepStatus
from henk.skills.runner import SkillRunner


def _skill():
    return Skill(
        name="demo",
        summary="",
        tags=[],
        tools_required=[],
        source_path="x.md",
        steps=[
            SkillStep(1, "Een", "Instr 1", "A1", "O1"),
            SkillStep(2, "Twee", "Instr 2", "A2", "O2"),
        ],
    )


def test_runner_executes_steps_sequentially():
    react = MagicMock()
    react.run.side_effect = ["r1", "r2"]
    gw = MagicMock()
    runner = SkillRunner(MagicMock(), gw, react)
    req = Requirements(task_description="taak")

    out = runner.run(_skill(), req)
    assert "Stap 2" in out
    assert react.run.call_count == 2


def test_runner_stops_on_failure():
    react = MagicMock()
    react.run.side_effect = ["ok", RuntimeError("boem")]
    gw = MagicMock()
    runner = SkillRunner(MagicMock(), gw, react)
    req = Requirements(task_description="taak")

    out = runner.run(_skill(), req)
    assert "mislukt" in out


def test_runner_prompt_includes_max_three_previous_results():
    runner = SkillRunner(MagicMock(), MagicMock(), MagicMock())
    step = SkillStep(4, "Vier", "Instr", "Act", "Out")
    req = Requirements(task_description="taak", specifications="- eis")
    prompt = runner._build_step_prompt(step, req, ["a", "b", "c", "d"])
    assert "- b" in prompt and "- d" in prompt
    assert "- a" not in prompt
