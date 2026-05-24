"""Provider boundaries for web research."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Callable, Protocol


class ResearchProvider(Protocol):
    provider_name: str

    def run(self, query: str) -> dict[str, Any]:
        """Return a structured WebResearchRun-like payload."""


class FakeResearchProvider:
    provider_name = "fake"

    def run(self, query: str) -> dict[str, Any]:
        clean_query = _require_query(query)
        return {
            "research_id": "research_fake_001",
            "query": clean_query,
            "provider": self.provider_name,
            "created_at": _utc_now(),
            "status": "ok",
            "evidence_status": "complete",
            "sources": [
                {
                    "source_id": "src_001",
                    "title": "Fake source-backed research note",
                    "url": "https://example.com/isotope-research",
                    "snippet": "Research claims should cite source ids.",
                    "why_used": "deterministic fake source for tests",
                    "retrieved_at": _utc_now(),
                    "provider_rank": 1,
                }
            ],
            "report": {
                "summary": f"Fake research summary for {clean_query}.",
                "claims": [
                    {
                        "text": "Research reports must keep source-backed claims.",
                        "source_ids": ["src_001"],
                        "confidence": "high",
                    }
                ],
                "limitations": ["fake provider"],
                "next_queries": [],
            },
            "provenance": {"provider": self.provider_name},
        }


class CodexDelegatedResearchProvider:
    provider_name = "codex_delegated"

    def __init__(self, backend: Callable[[str], str]):
        self.backend = backend

    def run(self, query: str) -> dict[str, Any]:
        clean_query = _require_query(query)
        prompt = build_codex_research_prompt(clean_query)
        raw_output = self.backend(prompt)
        payload = extract_research_json(raw_output)
        payload["query"] = clean_query
        payload["provider"] = self.provider_name
        payload.setdefault("provenance", {})
        payload["provenance"]["provider"] = self.provider_name
        payload["provenance"]["raw_output"] = raw_output
        payload.setdefault("created_at", _utc_now())
        payload.setdefault("research_id", "research_codex_delegated")
        payload.setdefault("status", "ok")
        payload.setdefault("evidence_status", "partial")
        return payload


def build_codex_research_prompt(query: str) -> str:
    clean_query = _require_query(query)
    return (
        "Research this query using web/search-capable reasoning if available. "
        "Return exactly one JSON object, no prose outside JSON. "
        "Required keys: research_id, created_at, status, evidence_status, sources, report. "
        "Each source must include source_id, title, url, snippet, why_used, retrieved_at. "
        "Each report claim must include text, source_ids, confidence. "
        f"Query: {clean_query}"
    )


def extract_research_json(raw_output: str) -> dict[str, Any]:
    if not isinstance(raw_output, str):
        raise ValueError("research output must be text")
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_output, flags=re.DOTALL)
    candidate = fenced.group(1) if fenced else raw_output.strip()
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValueError("research JSON object was not found") from exc
    if not isinstance(payload, dict):
        raise ValueError("research JSON object must be a dict")
    return payload


def _require_query(query: str) -> str:
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    return query.strip()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
