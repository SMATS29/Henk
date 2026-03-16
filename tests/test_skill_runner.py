import asyncio
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
    results = ["r1", "r2"]

    async def async_run(prompt, on_status=None, requirements=None):
        return results.pop(0)

    react.run = async_run
    gw = MagicMock()
    runner = SkillRunner(MagicMock(), gw, react)
    req = Requirements(task_description="taak")

    out = asyncio.run(runner.run(_skill(), req))
    assert "Stap 2" in out
    assert react.run is async_run  # Both steps were called


def test_runner_stops_on_failure():
    react = MagicMock()
    call_count = [0]

    async def async_run(prompt, on_status=None, requirements=None):
        call_count[0] += 1
        if call_count[0] == 1:
            return "ok"
        raise RuntimeError("boem")

    react.run = async_run
    gw = MagicMock()
    runner = SkillRunner(MagicMock(), gw, react)
    req = Requirements(task_description="taak")

    out = asyncio.run(runner.run(_skill(), req))
    assert "mislukt" in out


def test_runner_prompt_includes_max_three_previous_results():
    runner = SkillRunner(MagicMock(), MagicMock(), MagicMock())
    step = SkillStep(4, "Vier", "Instr", "Act", "Out")
    req = Requirements(task_description="taak", specifications="- eis")
    prompt = runner._build_step_prompt(step, req, ["a", "b", "c", "d"])
    assert "- b" in prompt and "- d" in prompt
    assert "- a" not in prompt
