from __future__ import annotations

from pathlib import Path

from isotope.llm.prompts import SYSTEM_PROMPT_NAMES, load_system_prompt


EXPECTED_SYSTEM_PROMPTS = (
    "agent_loop_planner",
    "capacity_calling",
    "desktop_chat",
    "goal_planning",
    "goal_planning_repair",
    "product_chat",
    "supervisor_llm_action",
    "supervisor_llm_summary",
    "workbench_ask",
)


def test_all_production_system_prompts_are_registered_md_assets():
    assert SYSTEM_PROMPT_NAMES == EXPECTED_SYSTEM_PROMPTS
    for name in EXPECTED_SYSTEM_PROMPTS:
        text = load_system_prompt(name)
        assert text
        assert not text.startswith("#")


def test_production_system_prompt_text_is_not_left_inline():
    source_root = Path(__file__).resolve().parents[3] / "src" / "isotope"
    offenders: list[str] = []
    for path in source_root.rglob("*.py"):
        if "/demo/" in path.as_posix():
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            if '"role": "system"' not in line:
                continue
            block = "\n".join(lines[index : index + 8])
            if '"content": "' in block or '"content": (' in block:
                offenders.append(path.relative_to(source_root).as_posix())
                break
    assert offenders == []
