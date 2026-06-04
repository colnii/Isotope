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


def test_model_facing_surfaces_do_not_train_conservative_semantics():
    violations = []
    for relative_path in MODEL_FACING_FILES:
        text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        for pattern in FORBIDDEN_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                violations.append(f"{relative_path}: {pattern}")

    assert violations == []
