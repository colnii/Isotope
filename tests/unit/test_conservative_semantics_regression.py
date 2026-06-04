from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

MODEL_FACING_FILES = [
    "src/isotope/agents/loop/context.py",
    "src/isotope/agents/loop/control.py",
    "src/isotope/capabilities/catalog.py",
    "src/isotope/capabilities/runner.py",
    "src/isotope/demo/agent_loop/matrix_scenarios.py",
    "src/isotope/demo/demo_planner_helpers.py",
    "src/isotope/features/supervisor/capability_gaps.py",
    "src/isotope/memory/__init__.py",
    "src/isotope/rag/sparse.py",
    "src/isotope/rag/ingestion.py",
]

FORBIDDEN_PATTERNS = [
    r"\b" + "Unavailable" + "Memory",
    r"\b" + "Unavailable" + "ExternalIngestionService" + r"\b",
    r"\bmemory" + "_query" + "_unavailable" + r"\b",
    r"\bsummary" + "_refs" + "_provenance" + "_only" + r"\b",
    r"\bpublic" + "_metadata" + "_summary" + "_only" + r"\b",
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
]


def test_model_facing_surfaces_do_not_train_conservative_semantics():
    violations = []
    for relative_path in MODEL_FACING_FILES:
        text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        for pattern in FORBIDDEN_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                violations.append(f"{relative_path}: {pattern}")

    assert violations == []
