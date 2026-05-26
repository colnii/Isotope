from __future__ import annotations

from isotope.features.research.models import ResearchSource


def test_research_source_round_trips_classification_fields():
    source = ResearchSource.from_dict(
        {
            "source_id": "src_001",
            "title": "Python documentation",
            "url": "https://docs.python.org/3/library/urllib.parse.html",
            "snippet": "URL parsing APIs.",
            "why_used": "official API reference",
            "retrieved_at": "2026-05-24T00:00:00Z",
            "provider_rank": 1,
            "source_kind": "official_docs",
            "source_authority": "high",
        }
    )

    assert source.source_kind == "official_docs"
    assert source.source_authority == "high"
    assert source.to_dict()["source_kind"] == "official_docs"
    assert source.to_dict()["source_authority"] == "high"


def test_research_source_defaults_missing_classification_to_unknown():
    source = ResearchSource.from_dict(
        {
            "source_id": "src_001",
            "title": "Legacy source",
            "url": "https://example.com/legacy",
            "snippet": "Legacy artifact content.",
            "why_used": "legacy report",
            "retrieved_at": "2026-05-24T00:00:00Z",
        }
    )

    assert source.source_kind == "unknown"
    assert source.source_authority == "unknown"
    assert source.to_dict()["source_kind"] == "unknown"
    assert source.to_dict()["source_authority"] == "unknown"
