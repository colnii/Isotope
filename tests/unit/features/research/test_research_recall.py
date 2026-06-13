from __future__ import annotations

import json

from isotope.features.research.recall import build_research_recall_payload
from isotope.workspace.artifacts import ArtifactStore


def test_research_recall_returns_preview_without_report_content(tmp_path):
    store = ArtifactStore(tmp_path)
    report = store.create_artifact(
        "run_research_a",
        execution_id="exec_research",
        artifact_type="research.report",
        summary="RAG substrate report preview for artifact retrieval.",
        content=json.dumps(
            {"secret": "raw report content must not leak through recall"},
            sort_keys=True,
        ),
        source_refs=[{"ref_type": "url", "url": "https://example.com/rag"}],
    )
    store.create_artifact(
        "run_research_a",
        execution_id="exec_research",
        artifact_type="research.raw_transcript",
        summary="RAG substrate transcript should not be indexed by recall.",
        content="transcript content must not leak through recall",
    )

    payload = build_research_recall_payload(
        root=tmp_path,
        query="artifact retrieval substrate",
        dense_retrieval={"backend": "local", "dimensions": 8},
    )

    assert payload["status"] == "ok"
    assert payload["content_policy"] == "research_report_artifact_preview_only"
    assert payload["summary"] == {"total": 1, "matched": 1, "hidden_artifacts": 0}
    assert payload["retrieval"] == {"backend": "hybrid", "dense_status": "ok"}
    assert payload["results"] == [
        {
            "run_id": "run_research_a",
            "artifact_id": report.artifact_id,
            "artifact_type": "research.report",
            "summary": "RAG substrate report preview for artifact retrieval.",
            "ref": report.ref.to_dict(),
            "source_refs": [{"ref_type": "url", "url": "https://example.com/rag"}],
            "provenance": {"execution_id": "exec_research"},
        }
    ]
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    assert "raw report content must not leak" not in encoded
    assert "transcript content must not leak" not in encoded


def test_research_recall_defaults_to_bm25_without_dense_config(tmp_path):
    ArtifactStore(tmp_path).create_artifact(
        "run_research_b",
        execution_id="exec_research",
        artifact_type="research.report",
        summary="BM25 fallback preview for research recall.",
        content="hidden report body",
    )

    payload = build_research_recall_payload(
        root=tmp_path,
        query="BM25 fallback",
    )

    assert payload["retrieval"] == {"backend": "bm25", "dense_status": "not_configured"}
    assert payload["summary"]["matched"] == 1


def test_research_recall_filters_by_run_id(tmp_path):
    store = ArtifactStore(tmp_path)
    excluded = store.create_artifact(
        "run_excluded",
        execution_id="exec_research",
        artifact_type="research.report",
        summary="Excluded artifact preview about unrelated topic.",
        content="excluded content must not leak",
    )
    included = store.create_artifact(
        "run_included",
        execution_id="exec_research",
        artifact_type="research.report",
        summary="Included artifact preview about launch gating.",
        content="included content must not leak",
    )

    payload = build_research_recall_payload(
        root=tmp_path,
        query="artifact preview",
        run_id="run_included",
        limit=10,
    )

    assert payload["summary"] == {"total": 1, "matched": 1, "hidden_artifacts": 0}
    assert [item["artifact_id"] for item in payload["results"]] == [
        included.artifact_id
    ]
    assert excluded.artifact_id not in json.dumps(payload, sort_keys=True)


def test_research_recall_rejects_empty_query(tmp_path):
    try:
        build_research_recall_payload(root=tmp_path, query=" ")
    except ValueError as exc:
        assert "query must be a non-empty string" in str(exc)
    else:
        raise AssertionError("empty query should fail")
