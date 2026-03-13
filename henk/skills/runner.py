from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from henk.requirements import Requirements
from henk.skills.models import Skill, SkillRun, SkillStep, StepStatus


class SkillRunner:
    """Voert skills stapsgewijs uit."""

    def __init__(self, brain: Any, gateway: Any, react_loop: Any):
        self._brain = brain
        self._gateway = gateway
        self._react_loop = react_loop

    def run(self, skill: Skill, requirements: Requirements, on_status: Callable[[str], None] | None = None) -> str:
        skill_run = SkillRun(skill=skill, started_at=datetime.now())
        results: list[str] = []

        while skill_run.active_step is not None:
            step = skill_run.active_step
            if on_status:
                on_status(f"Stap {step.number}/{len(skill.steps)}: {step.title}")
            step.status = StepStatus.ACTIVE
            self._gateway.log_skill_event("step.started", skill.name, step.number, step.title)

            try:
                step_prompt = self._build_step_prompt(step, requirements, results)
                result = self._react_loop.run(step_prompt, on_status=on_status)

                step.status = StepStatus.COMPLETED
                step.result = result
                results.append(f"Stap {step.number} ({step.title}): {result}")
                self._gateway.log_skill_event("step.completed", skill.name, step.number, step.title)
            except Exception as error:
                step.status = StepStatus.FAILED
                step.error = str(error)
                self._gateway.log_skill_event("step.failed", skill.name, step.number, str(error))
                return (
                    f"Stap {step.number} ({step.title}) is mislukt: {error}\n\n"
                    f"Eerdere resultaten:\n{'\n'.join(results)}"
                )

            skill_run.advance()

        skill_run.completed_at = datetime.now()
        return results[-1] if results else "Skill afgerond zonder resultaat."

    def _build_step_prompt(self, step: SkillStep, requirements: Requirements, previous_results: list[str]) -> str:
        parts = [
            f"## Actieve stap: {step.title}",
            f"\n{step.instruction}",
            f"\n**Actie:** {step.action}",
            f"**Verwachte output:** {step.expected_output}",
        ]

        if requirements.specifications:
            parts.append(f"\n## Eisen\n{requirements.specifications}")

        if previous_results:
            parts.append("\n## Eerdere stappen")
            for result in previous_results[-3:]:
                parts.append(f"- {result[:200]}")

        return "\n".join(parts)
