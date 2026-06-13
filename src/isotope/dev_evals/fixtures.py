from __future__ import annotations

import json
from pathlib import Path

from isotope.workspace.artifacts import ArtifactStore


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
    if fixture == "research_recall_seeded":
        _seed_research_recall_fixture(state_root)
    return state_root, workspace


def _seed_research_recall_fixture(state_root: Path) -> None:
    ArtifactStore(state_root).create_artifact(
        run_id="run_research_recall_eval",
        execution_id="exec_research_recall_eval",
        artifact_type="research.report",
        summary=(
            "RAG_RECALL_EVAL_MARKER stored report preview for prior "
            "research recall."
        ),
        content=json.dumps(
            {
                "query": "RAG_RECALL_EVAL_MARKER",
                "report": (
                    "Detailed raw report body for the seeded dev eval. "
                    "must_not_leak"
                ),
            },
            sort_keys=True,
        ),
        source_refs=[
            {
                "ref_type": "url",
                "url": "https://example.com/rag-recall-eval",
                "title": "RAG recall eval source",
            }
        ],
    )
