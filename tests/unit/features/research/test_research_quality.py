from __future__ import annotations

from isotope.features.research.quality import research_quality_summary


def _report_payload() -> dict:
    return {
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
            "next_queries": [],
        },
    }


def test_research_quality_summary_marks_source_backed_report_promotable():
    summary = research_quality_summary(_report_payload())

    assert summary == {
        "status": "promotable",
        "source_count": 1,
        "claim_count": 1,
        "source_backed_claim_count": 1,
        "uncited_claim_count": 0,
        "evidence_status": "complete",
        "reasons": [],
    }


def test_research_quality_summary_requires_complete_evidence_and_cited_claims():
    payload = _report_payload()
    payload["evidence_status"] = "incomplete_evidence"
    payload["report"]["claims"][0]["source_ids"] = []

    summary = research_quality_summary(payload)

    assert summary["status"] == "review_required"
    assert summary["source_backed_claim_count"] == 0
    assert summary["uncited_claim_count"] == 1
    assert summary["reasons"] == [
        "evidence_status_not_complete",
        "uncited_claims",
    ]
