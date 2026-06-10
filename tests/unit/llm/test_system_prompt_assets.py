from __future__ import annotations

from pathlib import Path

from isotope.llm.prompts import (
    PROMPT_TEMPLATE_NAMES,
    SYSTEM_PROMPT_NAMES,
    load_prompt_template,
    load_prompt_source,
    load_system_prompt,
    render_prompt_text,
)


EXPECTED_SYSTEM_PROMPTS = (
    "agent_group_member",
    "agent_loop_planner",
    "capacity_calling",
    "desktop_chat",
    "goal_planning",
    "goal_planning_repair",
    "product_chat",
    "social_participation",
    "social_reply",
    "supervisor_conversation_loop",
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
    "social_participation_user",
    "social_reply_user",
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
        "capacity_calling_user_allow_no_capacity": "capacity_id 设为 null",
        "goal_planning_user": "output_schema",
        "goal_planning_repair_user": "required_json_shape",
        "social_participation_user": "required_json_shape",
        "social_reply_user": "required_json_shape",
        "supervisor_llm_action_user": "decision_gate",
        "supervisor_llm_summary_user": "output_requirements",
        "workbench_ask_user": "output_requirements",
    }
    for name, fragment in expected_fragments.items():
        assert fragment in load_prompt_template(name)


def test_prompt_sources_separate_review_notes_from_runtime_sections():
    for name in PROMPT_TEMPLATE_NAMES:
        source = load_prompt_source(name)

        assert "# 给人看的说明，不会发送给模型" in source
        assert "# 发送给模型的真实提示词" in source
        assert f"<!-- prompt-section: {name} -->" in source
        assert "<!-- /prompt-section -->" in source


def test_supervisor_conversation_prompt_does_not_encode_fixed_intent_routes():
    prompt = load_prompt_template("supervisor_conversation_loop")

    forbidden = [
        "普通问候优先 direct_answer",
        "如果本轮已有 capacity_observation，优先基于 observation 输出 direct_answer",
        "已有 capacity_observation，优先基于 observation 输出 direct_answer",
        "明确要求访问、搜索或总结外部网页时，优先选择 `research.search`",
        "if project question",
        "if code request",
    ]
    for phrase in forbidden:
        assert phrase not in prompt

    assert "capacity_manifest" in prompt
    assert "capacity_observation" in prompt
    assert "call_capability" in prompt
    assert "report_capability_gap" in prompt


def test_supervisor_conversation_prompt_clarifies_manifest_runtime_evidence_boundary():
    prompt = load_prompt_template("supervisor_conversation_loop")

    assert "capacity_manifest 只能用于发现能力和构造调用" in prompt
    assert "capacity_observation / result projection 才是运行时证据" in prompt
    assert "不要把 capacity_manifest 当作执行结果" not in prompt
    assert "不要把“有这个能力”当成“已经得到结果”" not in prompt


def test_capacity_calling_prompts_are_a_single_reviewable_bundle():
    source = load_prompt_source("capacity_calling")

    assert "# 给人看的说明，不会发送给模型" in source
    assert "这个 prompt 只做一件事" in source
    assert "重点检查" in source
    assert "红线" in source
    assert "# 发送给模型的真实提示词" in source
    assert "<!-- prompt-section: capacity_calling -->" in source
    assert "<!-- prompt-section: capacity_calling_user -->" in source
    assert "<!-- prompt-section: capacity_calling_user_allow_no_capacity -->" in source

    system_prompt = load_system_prompt("capacity_calling")
    strict_user_prompt = load_prompt_template("capacity_calling_user")
    optional_user_prompt = load_prompt_template("capacity_calling_user_allow_no_capacity")

    assert system_prompt.startswith("你决定 Isotope 是否需要调用一个 capacity")
    assert '"goal": {{ goal }}' in strict_user_prompt
    assert '"capacities": {{ capacities }}' in strict_user_prompt
    assert "必须选择一个 capacity_id" in strict_user_prompt
    assert "可以不调用 capacity" in optional_user_prompt
    assert "capacity_id 设为 null" in optional_user_prompt


def test_goal_planning_prompt_reuses_conversation_research_context():
    prompt = load_prompt_template("goal_planning_user")

    assert "conversation.research_context" in prompt
    assert "不要把已完成的调研重新规划成搜索或资料搜集任务" in prompt


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
