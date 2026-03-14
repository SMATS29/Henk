from __future__ import annotations

from pathlib import Path

from henk.model_gateway import ModelGateway
from henk.router import ModelRole
from henk.skills.models import Skill
from henk.skills.parser import SkillParser


class SkillSelector:
    """Selecteert de juiste skill via samenvattingen."""

    def __init__(self, skills_dir: Path, model_gateway: ModelGateway):
        self._skills_dir = skills_dir
        self._model_gateway = model_gateway
        self._parser = SkillParser()

    def select(self, user_request: str) -> Skill | None:
        skills = self._load_all_skills()
        if not skills:
            return None

        summaries = "\n".join(f"- {skill.name}: {skill.summary}" for skill in skills)
        response = self._model_gateway.chat(
            role=ModelRole.FAST,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Verzoek: {user_request}\n\nBeschikbare skills:\n{summaries}\n\n"
                        "Welke skill past het best? Antwoord met alleen de skill-naam, "
                        "of 'geen' als geen skill past."
                    ),
                }
            ],
            system="Je bent een skill-selector. Kies de best passende skill of zeg 'geen'.",
            purpose="skill_select",
        ).response

        chosen_name = (response.text or "").strip().lower()
        for skill in skills:
            if skill.name.lower() == chosen_name:
                return skill
        return None

    def _load_all_skills(self) -> list[Skill]:
        if not self._skills_dir.exists():
            return []

        skills: list[Skill] = []
        for path in self._skills_dir.glob("*.md"):
            try:
                skills.append(self._parser.parse(path))
            except Exception:
                continue
        return skills
