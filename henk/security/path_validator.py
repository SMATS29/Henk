"""Padvalidatie met deny-by-default."""

from __future__ import annotations

from pathlib import Path


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def validate_read_path(path: str, read_roots: list[str]) -> str | None:
    """Valideer dat een pad binnen read_roots valt."""
    target = Path(path).expanduser().resolve()
    for root in read_roots:
        resolved_root = Path(root).expanduser().resolve()
        if _is_within(target, resolved_root):
            return str(target)
    return None


def validate_write_path(path: str, run_id: str, workspace_dir: str) -> str | None:
    """Valideer dat een pad binnen de workspace van deze run valt."""
    run_root = (Path(workspace_dir).expanduser() / run_id).resolve()
    target = Path(path).expanduser()
    if not target.is_absolute():
        target = run_root / target
    target = target.resolve()
    if _is_within(target, run_root):
        return str(target)
    return None
