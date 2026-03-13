from __future__ import annotations

import re
from pathlib import Path

import frontmatter

from henk.skills.models import Skill, SkillStep


_STEP_PATTERN = re.compile(r"^##\s+Stap\s+(\d+)\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE)


class SkillParser:
    """Parsed Markdown skill-documenten."""

    def parse(self, file_path: Path) -> Skill:
        post = frontmatter.load(file_path)
        name = str(post.metadata.get("name", "")).strip()
        summary = str(post.metadata.get("summary", "")).strip()
        tags = list(post.metadata.get("tags", []))
        tools_required = list(post.metadata.get("tools_required", []))

        if not name:
            raise ValueError(f"Skill mist 'name' in frontmatter: {file_path}")

        content = post.content
        matches = list(_STEP_PATTERN.finditer(content))
        if not matches:
            raise ValueError(f"Skill bevat geen stappen: {file_path}")

        steps: list[SkillStep] = []
        for index, match in enumerate(matches):
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
            block = content[start:end].strip()
            title = match.group(2).strip()
            number = int(match.group(1))

            action = self._extract_field(block, "Actie")
            expected_output = self._extract_field(block, "Output")
            if not action:
                action = block

            steps.append(
                SkillStep(
                    number=number,
                    title=title,
                    instruction=block,
                    action=action,
                    expected_output=expected_output or "",
                )
            )

        return Skill(
            name=name,
            summary=summary,
            tags=[str(tag) for tag in tags],
            tools_required=[str(tool) for tool in tools_required],
            steps=steps,
            source_path=str(file_path),
        )

    def _extract_field(self, block: str, name: str) -> str | None:
        pattern = re.compile(rf"\*\*{name}:\*\*\s*(.+)", re.IGNORECASE)
        match = pattern.search(block)
        if not match:
            return None
        return match.group(1).strip()
