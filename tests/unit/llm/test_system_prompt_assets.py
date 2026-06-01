from __future__ import annotations

from pathlib import Path

from isotope.llm.prompts import (
    PROMPT_TEMPLATE_NAMES,
    SYSTEM_PROMPT_NAMES,
    load_prompt_template,
    load_system_prompt,
    render_prompt_text,
)


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

EXPECTED_PROMPT_TEMPLATES = EXPECTED_SYSTEM_PROMPTS + (
    "agent_loop_planner_user",
    "capacity_calling_user",
    "capacity_calling_user_allow_no_capacity",
    "goal_planning_user",
    "goal_planning_repair_user",
    "supervisor_llm_action_user",
    "supervisor_llm_summary_user",
    "workbench_ask_user",
)


def test_all_production_system_prompts_are_registered_md_assets():
    assert SYSTEM_PROMPT_NAMES == EXPECTED_SYSTEM_PROMPTS
    for name in EXPECTED_SYSTEM_PROMPTS:
        text = load_system_prompt(name)
        assert text
        assert not text.startswith("#")


def test_all_production_prompt_templates_are_registered_md_assets():
    assert PROMPT_TEMPLATE_NAMES == EXPECTED_PROMPT_TEMPLATES
    expected_fragments = {
        "agent_loop_planner_user": "required_json_shape",
        "capacity_calling_user": "required_json_shape",
        "capacity_calling_user_allow_no_capacity": "set capacity_id to null",
        "goal_planning_user": "output_schema",
        "goal_planning_repair_user": "required_json_shape",
        "supervisor_llm_action_user": "decision_gate",
        "supervisor_llm_summary_user": "output_requirements",
        "workbench_ask_user": "output_requirements",
    }
    for name, fragment in expected_fragments.items():
        assert fragment in load_prompt_template(name)


def test_prompt_template_renderer_replaces_placeholders_and_rejects_missing_values():
    rendered = render_prompt_text(
        "before {{ first }} middle {{second}} after",
        {"first": "one", "second": "two"},
    )

    assert rendered == "before one middle two after"

    try:
        render_prompt_text("{{ missing }}", {})
    except ValueError as exc:
        assert "missing prompt template variables: missing" in str(exc)
    else:
        raise AssertionError("missing prompt variable should fail")


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


def test_static_user_prompt_contracts_are_not_left_inline():
    source_root = Path(__file__).resolve().parents[3] / "src" / "isotope"
    prompt_builder_paths = (
        "agents/loop/provider_planner.py",
        "llm/capacity_calling.py",
        "features/ask/flow.py",
        "features/supervisor/planner/goal_planner.py",
        "features/supervisor/llm_action/prompt.py",
        "features/supervisor/llm_action/llm_summary.py",
    )
    forbidden_fragments = (
        '"accepted_output_formats"',
        '"action_rules"',
        '"context_capability"',
        '"decision_gate"',
        '"output_requirements"',
        '"output_schema"',
        '"required_json_shape"',
        '"worker_profiles"',
    )
    offenders: list[str] = []
    for relative in prompt_builder_paths:
        source = (source_root / relative).read_text(encoding="utf-8")
        for fragment in forbidden_fragments:
            if fragment in source:
                offenders.append(f"{relative}: {fragment}")
    assert offenders == []
