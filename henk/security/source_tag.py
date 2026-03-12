"""Bronlabels voor tool-output."""


def tag_output(tool_name: str, content: str, external: bool = False) -> str:
    """Tag tool-output met bron."""
    tag = f"[TOOL:{tool_name} — EXTERNAL]" if external else f"[TOOL:{tool_name}]"
    return f"{tag}\n{content}\n[/TOOL:{tool_name}]"
