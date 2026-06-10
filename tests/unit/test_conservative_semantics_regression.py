from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

MODEL_FACING_FILES = [
    "README.md",
    "docs/current/README.md",
    "docs/current/agent-task-queue.md",
    "docs/current/codex-supervisor-guide.md",
    "docs/current/docs-map.md",
    "docs/current/supervisor-command-reference.md",
    "docs/current/terminology.md",
    "src/isotope/agents/loop/context.py",
    "src/isotope/agents/loop/control.py",
    "src/isotope/capabilities/catalog.py",
    "src/isotope/capabilities/code_access.py",
    "src/isotope/capabilities/extensions.py",
    "src/isotope/capabilities/memory.py",
    "src/isotope/capabilities/runner.py",
    "src/isotope/capabilities/screen.py",
    "src/isotope/capabilities/supervisor.py",
    "src/isotope/capabilities/vcs.py",
    "src/isotope/capabilities/workspace_files.py",
    "src/isotope/demo/agent_loop/matrix_scenarios.py",
    "src/isotope/demo/demo_artifact_review_scenarios.py",
    "src/isotope/demo/demo_planner_helpers.py",
    "src/isotope/demo/demo_trace_format.py",
    "src/isotope/demo/demo_workspace_scenarios.py",
    "src/isotope/features/supervisor/capability_gaps.py",
    "src/isotope/features/supervisor/adoption/tmux_discovery.py",
    "src/isotope/features/supervisor/commands/parser/__init__.py",
    "src/isotope/features/supervisor/conversation_loop.py",
    "src/isotope/features/supervisor/desktop_chat.py",
    "src/isotope/features/supervisor/desktop_snapshot.py",
    "src/isotope/features/supervisor/flow/_flow_impl.py",
    "src/isotope/features/supervisor/replan.py",
    "src/isotope/features/supervisor/runner.py",
    "src/isotope/features/supervisor/state/projection.py",
    "src/isotope/features/supervisor/workers/integration_review.py",
    "src/isotope/extensions/skills.py",
    "src/isotope/execution/terminal/windows_smoke.py",
    "src/isotope/integrations/codex/session_reader.py",
    "src/isotope/memory/__init__.py",
    "src/isotope/memory/views.py",
    "src/isotope/platform/state/multi_worker.py",
    "src/isotope/platform/state/projector/handlers.py",
    "src/isotope/rag/sparse.py",
    "src/isotope/rag/ingestion.py",
    "src/isotope/runtime/in_process/actions.py",
    "src/isotope/workspace/__init__.py",
]

CURRENT_ENTRY_FILES = [
    "README.md",
    "docs/current/README.md",
    "docs/current/agent-task-queue.md",
    "docs/current/codex-supervisor-guide.md",
    "docs/current/docs-map.md",
    "docs/current/supervisor-command-reference.md",
    "docs/current/terminology.md",
]

SUPERPOWERS_SPEC_FILES = [
    "docs/superpowers/specs/2026-06-03-state-memory-artifact-projection-design.md",
    "docs/superpowers/specs/2026-06-04-agent-group-chat-design.md",
    "docs/superpowers/specs/2026-06-04-desktop-chat-golden-path-design.md",
    "docs/superpowers/specs/2026-06-04-native-coding-product-maturity-design.md",
    "docs/superpowers/specs/2026-06-04-qq-group-chatbot-complete-design.md",
    "docs/superpowers/specs/2026-06-04-skills-mcp-client-bridge-design.md",
    "docs/superpowers/specs/2026-06-04-vector-hybrid-retrieval-design.md",
]

SUPERPOWERS_PLAN_FILES = [
    "docs/superpowers/plans/2026-06-03-native-coding-foundations.md",
    "docs/superpowers/plans/2026-06-03-state-memory-artifact-projections.md",
    "docs/superpowers/plans/2026-06-04-agent-group-chat-runtime.md",
    "docs/superpowers/plans/2026-06-04-desktop-chat-golden-path.md",
    "docs/superpowers/plans/2026-06-04-native-coding-product-maturity.md",
    "docs/superpowers/plans/2026-06-04-native-coding-reviewed-apply-handoff.md",
    "docs/superpowers/plans/2026-06-04-skills-mcp-client-bridge.md",
    "docs/superpowers/plans/2026-06-04-supervisor-memory-recall.md",
    "docs/superpowers/plans/2026-06-04-supervisor-worker-lifecycle-decision.md",
    "docs/superpowers/plans/2026-06-04-vector-hybrid-retrieval.md",
]

LLM_PROMPT_FILES = [
    "src/isotope/llm/prompts/agent_loop/group_member.prompt.md",
    "src/isotope/llm/prompts/agent_loop/planner.prompt.md",
    "src/isotope/llm/prompts/capacity/calling.prompt.md",
    "src/isotope/llm/prompts/chat/desktop.prompt.md",
    "src/isotope/llm/prompts/chat/product.prompt.md",
    "src/isotope/llm/prompts/social/participation.prompt.md",
    "src/isotope/llm/prompts/social/reply.prompt.md",
    "src/isotope/llm/prompts/supervisor/conversation_loop.prompt.md",
    "src/isotope/llm/prompts/supervisor/goal_planning.prompt.md",
    "src/isotope/llm/prompts/supervisor/llm_action.prompt.md",
    "src/isotope/llm/prompts/supervisor/llm_summary.prompt.md",
    "src/isotope/llm/prompts/workbench/ask.prompt.md",
]

FORBIDDEN_PATTERNS = [
    r"\b" + "Unavailable" + "Memory",
    r"\b" + "Unavailable" + "ExternalIngestionService" + r"\b",
    r"\bmemory" + "_query" + "_unavailable" + r"\b",
    r"\bsummary" + "_refs" + "_provenance" + "_only" + r"\b",
    r"\bsummary" + "_only" + r"\b",
    r"\bpublic" + "_metadata" + "_summary" + "_only" + r"\b",
    r"\brequested" + "_action" + "_summary" + r"\b",
    r"\bpreview" + "_only" + r"\b",
    r"\bview" + "_only" + r"\b",
    r"\bfuture\b",
    r"\bqueued" + "_capabilities" + r"\b",
    r"\bblocked" + "_queued" + r"\b",
    r"\bapp" + "_queued" + "_friction" + r"\b",
    r"\bdisabled capability\b",
    r"\bfailed" + "_closed" + r"\b",
    r"\bnot[- ]enabled\b",
    r"\blow[-_ ]sensitive\b",
    r"\bdeterministic" + "_readonly" + r"\b",
    r"\bread" + "_only(?=_)",
    r"\bread" + "_only" + r"\b",
    r"\b" + "readonly" + r"\b",
    r"\bread" + "-only" + r"\b",
    r"\b" + "bounded" + r"\b",
]

CURRENT_ENTRY_FORBIDDEN_PATTERNS = [
    "低敏",
    "只读",
    "预检",
    "不默认",
    "默认不开",
    "不能",
    "不应",
]

CURRENT_ENTRY_NEGATIVE_ACTION_PATTERNS = [
    "不删除",
    "不合并",
    "不返回",
    "不读取",
    "不写",
    "不直接",
    "不生成",
    "不" + "执行",
    "不会",
    "不打开",
    "不启动",
    "不修改",
    "不阻止",
    "不落",
    "不自动",
    "不清理",
    "暂不",
]

CURRENT_ENTRY_DEFERRED_EXECUTION_PATTERNS = [
    "默认" + "只" + "生成",
    "当前" + "只" + "生成",
    "显式开关后才走",
    "低风险" + "能力",
    "默认 " + "preflight",
    "pre" + "flight",
    "defer" + "red",
    "planned " + "provider",
    "fail " + "closed",
]

SUPERPOWERS_SPEC_FORBIDDEN_PATTERNS = [
    r"\blow[-_ ]sensitive\b",
    r"\b" + "bounded" + r"\b",
    r"\bread[-_ ]only\b",
    r"\b" + "readonly" + r"\b",
    r"\bsummary[-_ ]only\b",
    r"\bpreview[-_ ]only\b",
    r"\bfail[-_ ]closed\b",
    r"\bnot[-_ ]enabled\b",
    r"\b" + "deferred" + r"\b",
    r"\b" + "preflight" + r"\b",
]

SUPERPOWERS_PLAN_PROSE_FORBIDDEN_PATTERNS = SUPERPOWERS_SPEC_FORBIDDEN_PATTERNS

LLM_PROMPT_FORBIDDEN_TERMS = [
    "低敏",
    "只读",
    "预检",
    "不默认",
    "默认不开",
    "fail_closed",
    "not_enabled",
    "deferred",
    "preflight",
    "low-sensitive",
    "low_sensitive",
    "read-only",
    "readonly",
    "summary-only",
    "preview-only",
]

ENTRYPOINT_CONTRACT_FILES = [
    "src/isotope/capabilities/coding.py",
    "src/isotope/integrations/codex/cli.py",
    "src/isotope/demo/demo_trace_format.py",
]

ENTRYPOINT_CONTRACT_FORBIDDEN_TERMS = [
    "preview-only",
    "coding_task.preview",
    "deterministic_preview",
    "read-only in this first slice",
    "approval_policy must be never in this first slice",
    "低敏摘要",
]


def _markdown_prose_lines(text: str) -> list[tuple[int, str]]:
    prose_lines = []
    in_fenced_block = False
    for line_number, line in enumerate(text.splitlines(), start=1):
        if line.startswith("```"):
            in_fenced_block = not in_fenced_block
            continue
        if in_fenced_block:
            continue
        prose_lines.append((line_number, re.sub(r"`[^`]+`", "", line)))
    return prose_lines


def test_model_facing_surfaces_do_not_train_conservative_semantics():
    violations = []
    for relative_path in MODEL_FACING_FILES:
        text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        for pattern in FORBIDDEN_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                violations.append(f"{relative_path}: {pattern}")

    assert violations == []


def test_entrypoint_contracts_do_not_keep_disabled_shell_language():
    violations = []
    for relative_path in ENTRYPOINT_CONTRACT_FILES:
        text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        for term in ENTRYPOINT_CONTRACT_FORBIDDEN_TERMS:
            if term in text:
                violations.append(f"{relative_path}: {term}")

    assert violations == []


def test_current_entry_docs_do_not_train_guardrail_first_chinese_language():
    violations = []
    for relative_path in CURRENT_ENTRY_FILES:
        text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        for pattern in CURRENT_ENTRY_FORBIDDEN_PATTERNS:
            if pattern in text:
                violations.append(f"{relative_path}: {pattern}")

    assert violations == []


def test_current_entry_docs_use_positive_execution_path_language():
    violations = []
    for relative_path in CURRENT_ENTRY_FILES:
        text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        for pattern in CURRENT_ENTRY_NEGATIVE_ACTION_PATTERNS:
            if pattern in text:
                violations.append(f"{relative_path}: {pattern}")

    assert violations == []


def test_current_entry_docs_do_not_describe_capacity_as_deferred_execution():
    violations = []
    for relative_path in CURRENT_ENTRY_FILES:
        text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        for pattern in CURRENT_ENTRY_DEFERRED_EXECUTION_PATTERNS:
            if pattern in text:
                violations.append(f"{relative_path}: {pattern}")

    assert violations == []


def test_superpowers_specs_do_not_retrain_conservative_design_language():
    violations = []
    for relative_path in SUPERPOWERS_SPEC_FILES:
        text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        for pattern in SUPERPOWERS_SPEC_FORBIDDEN_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                violations.append(f"{relative_path}: {pattern}")

    assert violations == []


def test_superpowers_plan_prose_does_not_retrain_conservative_design_language():
    violations = []
    for relative_path in SUPERPOWERS_PLAN_FILES:
        text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        for line_number, prose_line in _markdown_prose_lines(text):
            for pattern in SUPERPOWERS_PLAN_PROSE_FORBIDDEN_PATTERNS:
                if re.search(pattern, prose_line, re.IGNORECASE):
                    violations.append(f"{relative_path}:{line_number}: {pattern}")

    assert violations == []


def test_llm_prompts_do_not_train_conservative_design_language():
    violations = []
    for relative_path in LLM_PROMPT_FILES:
        text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        for term in LLM_PROMPT_FORBIDDEN_TERMS:
            if term in text:
                violations.append(f"{relative_path}: {term}")

    assert violations == []
