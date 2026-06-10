from __future__ import annotations

from pathlib import Path


def prepare_fixture(root: Path, fixture: str) -> tuple[Path, Path]:
    state_root = root / "state"
    workspace = root / "workspace"
    state_root.mkdir(parents=True, exist_ok=True)
    workspace.mkdir(parents=True, exist_ok=True)
    if fixture in {"workspace_with_code", "workspace_with_diff"}:
        src = workspace / "src"
        src.mkdir(parents=True, exist_ok=True)
        (src / "app.py").write_text(
            "ISOTOPE_DEV_EVAL_MARKER = 'present'\n"
            "def answer():\n"
            "    return ISOTOPE_DEV_EVAL_MARKER\n",
            encoding="utf-8",
        )
    if fixture == "workspace_with_diff":
        (workspace / "changed.txt").write_text("changed\n", encoding="utf-8")
    return state_root, workspace
