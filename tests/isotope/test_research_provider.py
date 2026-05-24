from __future__ import annotations

import json

import pytest

from isotope.features.research.providers import (
    CodexDelegatedResearchProvider,
    FakeResearchProvider,
    extract_research_json,
)


def test_fake_research_provider_returns_source_backed_report():
    provider = FakeResearchProvider()

    payload = provider.run("agent memory retrieval")

    assert payload["query"] == "agent memory retrieval"
    assert payload["provider"] == "fake"
    assert payload["sources"][0]["source_id"] == "src_001"
    assert payload["report"]["claims"][0]["source_ids"] == ["src_001"]


def test_extract_research_json_accepts_fenced_json():
    raw = 'prefix\n```json\n{"status":"ok","sources":[]}\n```\nsuffix'

    assert extract_research_json(raw) == {"status": "ok", "sources": []}


def test_extract_research_json_rejects_missing_json_object():
    with pytest.raises(ValueError, match="research JSON object"):
        extract_research_json("no structured payload")


def test_codex_delegated_provider_builds_research_prompt():
    calls = []

    def backend(prompt: str) -> str:
        calls.append(prompt)
        return json.dumps(FakeResearchProvider().run("agent memory retrieval"))

    provider = CodexDelegatedResearchProvider(backend=backend)
    payload = provider.run("agent memory retrieval")

    assert payload["provider"] == "codex_delegated"
    assert "sources" in calls[0]
    assert "report" in calls[0]
