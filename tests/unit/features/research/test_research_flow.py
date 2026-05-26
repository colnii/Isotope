from __future__ import annotations

import json

from isotope.features.research.flow import ResearchFlow
from isotope.features.research.providers import FakeResearchProvider, ResearchProviderError


def test_research_flow_persists_raw_and_normalized_artifacts(tmp_path):
    flow = ResearchFlow.in_process(tmp_path, provider=FakeResearchProvider())

    result = flow.search("agent memory retrieval")

    payload = result.to_dict()
    assert payload["status"] == "ok"
    assert payload["research"]["evidence_status"] == "complete"
    assert len(payload["artifact_refs"]) == 2
    assert payload["artifacts"] == [
        {
            "artifact_type": "research.raw_transcript",
            "ref": result.artifact_refs[0].to_dict(),
            "summary": "raw research provider output: agent memory retrieval",
        },
        {
            "artifact_type": "research.report",
            "ref": result.artifact_refs[1].to_dict(),
            "summary": "Fake research summary for agent memory retrieval.",
        },
    ]
    records = [
        flow.core.runtime.get_artifact_record(ref)
        for ref in result.artifact_refs
    ]
    assert [record["artifact_type"] for record in records] == [
        "research.raw_transcript",
        "research.report",
    ]
    assert records[1]["summary"] == "Fake research summary for agent memory retrieval."


def test_research_flow_marks_missing_sources_incomplete(tmp_path):
    class NoSourcesProvider:
        provider_name = "no_sources"

        def run(self, query: str) -> dict:
            return {
                "research_id": "research_no_sources",
                "query": query,
                "provider": "no_sources",
                "created_at": "2026-05-24T00:00:00Z",
                "status": "ok",
                "evidence_status": "complete",
                "sources": [],
                "report": {"summary": "no sources"},
                "provenance": {"provider": "no_sources"},
            }

    flow = ResearchFlow.in_process(tmp_path, provider=NoSourcesProvider())

    result = flow.search("unsupported claim")

    assert result.research.evidence_status == "incomplete_evidence"
    normalized = flow.core.runtime.get_artifact_record(result.artifact_refs[1])
    assert normalized["artifact_type"] == "research.report"


def test_research_flow_rejects_unknown_claim_source_without_success_artifact(tmp_path):
    class BadClaimProvider:
        provider_name = "bad_claim"

        def run(self, query: str) -> dict:
            return {
                "research_id": "research_bad_claim",
                "query": query,
                "provider": "bad_claim",
                "created_at": "2026-05-24T00:00:00Z",
                "status": "ok",
                "evidence_status": "complete",
                "sources": [
                    {
                        "source_id": "src_001",
                        "title": "Bad source",
                        "url": "https://example.com/bad",
                        "snippet": "bad",
                        "why_used": "test",
                        "retrieved_at": "2026-05-24T00:00:00Z",
                    }
                ],
                "report": {
                    "summary": "bad claim",
                    "claims": [{"text": "bad", "source_ids": ["missing"]}],
                },
                "provenance": {"provider": "bad_claim"},
            }

    flow = ResearchFlow.in_process(tmp_path, provider=BadClaimProvider())

    result = flow.search("bad claim")

    assert result.status == "validation_failed"
    assert result.research is None
    assert result.artifact_refs == ()
    assert "unknown source_id" in result.error["message"]


def test_research_flow_marks_provider_errors_without_success_artifact(tmp_path):
    class FailingProvider:
        provider_name = "failing"

        def run(self, query: str) -> dict:
            raise ResearchProviderError(
                "codex cli did not return an agent message",
                details={
                    "codex_error_messages": ["Reconnecting... 2/5 (request timed out)"],
                    "codex_has_agent_message": False,
                    "codex_timeout_seconds": 120,
                },
            )

    flow = ResearchFlow.in_process(tmp_path, provider=FailingProvider())

    result = flow.search("python docs")

    assert result.status == "provider_failed"
    assert result.research is None
    assert len(result.artifact_refs) == 1
    assert result.error == {
        "code": "research_provider_failed",
        "details": {
            "codex_error_messages": ["Reconnecting... 2/5 (request timed out)"],
            "codex_has_agent_message": False,
            "codex_timeout_seconds": 120,
        },
        "message": "codex cli did not return an agent message",
        "retryable": True,
    }
    payload = result.to_dict()
    assert payload["query"] == "python docs"
    assert payload["artifacts"] == [
        {
            "artifact_type": "research.provider_trace",
            "ref": result.artifact_refs[0].to_dict(),
            "summary": "provider failure trace: python docs",
        }
    ]
    trace_record = flow.core.runtime.get_artifact_record(result.artifact_refs[0])
    assert trace_record["artifact_type"] == "research.provider_trace"
    assert trace_record["summary"] == "provider failure trace: python docs"
    trace_content = json.loads(flow.core.runtime.artifact_store.get_content(result.artifact_refs[0]))
    assert trace_content == {
        "error": {
            "code": "research_provider_failed",
            "details": {
                "codex_error_messages": ["Reconnecting... 2/5 (request timed out)"],
                "codex_has_agent_message": False,
                "codex_timeout_seconds": 120,
            },
            "message": "codex cli did not return an agent message",
            "retryable": True,
        },
        "provider": "failing",
        "query": "python docs",
        "status": "provider_failed",
    }


def test_research_flow_preserves_non_retryable_provider_preflight_trace(tmp_path):
    class MissingConfigProvider:
        provider_name = "tavily"

        def run(self, query: str) -> dict:
            raise ResearchProviderError(
                "tavily provider requires TAVILY_API_KEY",
                details={
                    "provider_id": "tavily",
                    "error_code": "missing_api_key",
                    "required_env": "TAVILY_API_KEY",
                    "retryable": False,
                },
            )

    flow = ResearchFlow.in_process(tmp_path, provider=MissingConfigProvider())

    result = flow.search("agent memory retrieval")

    assert result.status == "provider_failed"
    assert result.error["retryable"] is False
    trace_content = json.loads(flow.core.runtime.artifact_store.get_content(result.artifact_refs[0]))
    assert trace_content["provider"] == "tavily"
    assert trace_content["error"]["retryable"] is False
    assert trace_content["error"]["details"]["error_code"] == "missing_api_key"


def test_research_flow_persists_retry_attempt_details_in_provider_trace(tmp_path):
    class FailingProvider:
        provider_name = "codex_delegated"

        def run(self, query: str) -> dict:
            raise ResearchProviderError(
                "codex cli did not return an agent message: request timed out",
                details={
                    "attempt_count": 2,
                    "retry_exhausted": True,
                    "attempts": [
                        {
                            "attempt": 1,
                            "message": "codex cli did not return an agent message: request timed out",
                            "retryable": True,
                            "details": {
                                "codex_error_messages": ["request timed out on attempt 1"],
                            },
                        },
                        {
                            "attempt": 2,
                            "message": "codex cli did not return an agent message: request timed out",
                            "retryable": True,
                            "details": {
                                "codex_error_messages": ["request timed out on attempt 2"],
                            },
                        },
                    ],
                },
            )

    flow = ResearchFlow.in_process(tmp_path, provider=FailingProvider())

    result = flow.search("python docs")

    trace_content = json.loads(flow.core.runtime.artifact_store.get_content(result.artifact_refs[0]))
    assert trace_content["error"]["details"]["attempt_count"] == 2
    assert trace_content["error"]["details"]["retry_exhausted"] is True
    assert [attempt["attempt"] for attempt in trace_content["error"]["details"]["attempts"]] == [1, 2]
    assert trace_content["error"]["details"]["attempts"][0]["retryable"] is True


def test_research_report_can_be_found_through_artifact_record(tmp_path):
    flow = ResearchFlow.in_process(tmp_path, provider=FakeResearchProvider())

    result = flow.search("agent memory retrieval")
    record = flow.core.runtime.get_artifact_record(result.artifact_refs[1])

    assert record["artifact_type"] == "research.report"
    assert "Fake research summary" in record["summary"]
    assert record["source_refs"] == [result.artifact_refs[0].to_dict()]
