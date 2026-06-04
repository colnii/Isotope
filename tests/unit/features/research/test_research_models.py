from __future__ import annotations

import pytest

from isotope.features.research.models import WebResearchRun


def _valid_payload() -> dict:
    return {
        "research_id": "research_001",
        "query": "agent memory retrieval",
        "provider": "codex_delegated",
        "created_at": "2026-05-24T00:00:00Z",
        "status": "ok",
        "evidence_status": "complete",
        "sources": [
            {
                "source_id": "src_001",
                "title": "Retrieval design",
                "url": "https://example.com/retrieval",
                "snippet": "retrieval with provenance",
                "why_used": "explains source-backed retrieval",
                "retrieved_at": "2026-05-24T00:00:00Z",
                "provider_rank": 1,
            }
        ],
        "report": {
            "summary": "Retrieval should keep provenance.",
            "claims": [
                {
                    "text": "Claims need source refs.",
                    "source_ids": ["src_001"],
                    "confidence": "medium",
                }
            ],
            "limitations": ["single source"],
            "next_queries": ["controlled expand grants"],
        },
        "provenance": {"provider": "codex_delegated"},
    }


def test_web_research_run_requires_source_backed_claims():
    run = WebResearchRun.from_dict(_valid_payload())

    assert run.evidence_status == "complete"
    assert run.to_dict()["report"]["claims"][0]["source_ids"] == ["src_001"]


def test_web_research_run_fixture_uses_real_provider_name():
    payload = _valid_payload()

    assert payload["provider"] == "codex_delegated"
    assert payload["provenance"]["provider"] == "codex_delegated"


def test_web_research_run_marks_missing_sources_as_incomplete_evidence():
    payload = _valid_payload()
    payload["sources"] = []
    payload["evidence_status"] = "complete"

    run = WebResearchRun.from_dict(payload)

    assert run.evidence_status == "incomplete_evidence"


def test_web_research_run_rejects_claims_with_unknown_source_ids():
    payload = _valid_payload()
    payload["report"]["claims"][0]["source_ids"] = ["missing_src"]

    with pytest.raises(ValueError, match="unknown source_id"):
        WebResearchRun.from_dict(payload)
