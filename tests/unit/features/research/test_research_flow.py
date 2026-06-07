from __future__ import annotations

import json

from isotope.features.research.flow import ResearchFlow
from isotope.features.research.providers import ResearchProviderError
from isotope.features.research.tavily import TavilyResearchProvider


class _TestProvider:
    provider_name = "test"

    def run(self, query: str) -> dict:
        from isotope.features.research.providers import _utc_now
        from isotope.features.research.source_classification import classify_research_source
        source = {
            "source_id": "src_001",
            "title": "Test source",
            "url": "https://example.com/test",
            "snippet": "Test snippet.",
            "why_used": "test",
            "retrieved_at": _utc_now(),
            "provider_rank": 1,
        }
        source.update(classify_research_source(source))
        return {
            "research_id": "test_001",
            "query": query,
            "provider": self.provider_name,
            "created_at": _utc_now(),
            "status": "ok",
            "evidence_status": "complete",
            "sources": [source],
            "report": {
                "summary": f"Test summary for {query}.",
                "claims": [{"text": "Test claim.", "source_ids": ["src_001"], "confidence": "high"}],
                "limitations": [],
                "next_queries": [],
            },
            "provenance": {"provider": self.provider_name},
        }


def test_research_flow_persists_raw_and_normalized_artifacts(tmp_path):
    flow = ResearchFlow.in_process(tmp_path, provider=_TestProvider())

    result = flow.search("agent memory retrieval")

    payload = result.to_dict()
    assert payload["status"] == "ok"
    assert payload["research"]["evidence_status"] == "complete"
    assert payload["research"]["sources"][0]["source_kind"] == "unknown"
    assert payload["research"]["sources"][0]["source_authority"] == "unknown"
    assert len(payload["artifact_refs"]) == 2
    assert payload["artifacts"] == [
        {
            "artifact_type": "research.raw_transcript",
            "ref": result.artifact_refs[0].to_dict(),
            "summary": "Raw provider payload for research query: agent memory retrieval",
        },
        {
            "artifact_type": "research.report",
            "ref": result.artifact_refs[1].to_dict(),
            "summary": (
                "Research report for agent memory retrieval: "
                "Test summary for agent memory retrieval."
            ),
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
    assert records[1]["summary"] == (
        "Research report for agent memory retrieval: "
        "Test summary for agent memory retrieval."
    )


def test_research_flow_persists_tavily_execution_artifacts(tmp_path):
    def http_post(url, *, headers, payload, timeout_seconds):
        return {
            "query": payload["query"],
            "results": [
                {
                    "title": "Isotope research note",
                    "url": "https://example.com/research-note",
                    "content": "Research claims should cite source-backed snippets.",
                    "score": 0.91,
                }
            ],
            "response_time": 0.42,
            "usage": {"credits": 1},
        }

    flow = ResearchFlow.in_process(
        tmp_path,
        provider=TavilyResearchProvider(
            api_key="test-key",
            enable_network=True,
            http_post=http_post,
        ),
    )

    result = flow.search("agent memory retrieval")

    assert result.status == "ok"
    assert [artifact["artifact_type"] for artifact in result.artifacts] == [
        "research.raw_transcript",
        "research.report",
    ]
    raw_content = json.loads(flow.core.runtime.artifact_store.get_content(result.artifact_refs[0]))
    report_content = json.loads(flow.core.runtime.artifact_store.get_content(result.artifact_refs[1]))
    assert raw_content["provider"] == "tavily"
    assert report_content["sources"][0]["url"] == "https://example.com/research-note"
    assert report_content["report"]["claims"][0]["source_ids"] == ["src_001"]


def test_research_flow_persists_exact_url_extracted_report(tmp_path):
    def http_get(url, *, timeout_seconds):
        return {
            "url": url,
            "content_type": "text/html; charset=utf-8",
            "text": """
                <html>
                  <head><title>Exact URL Article</title></head>
                  <body>
                    <article>
                      <h1>Exact URL Article</h1>
                      <p>这是真实 URL 正文第一段，用于验证 summary。</p>
                      <p>这是真实 URL 正文第二段，用于验证 source preview。</p>
                    </article>
                  </body>
                </html>
            """,
        }

    flow = ResearchFlow.in_process(
        tmp_path,
        provider=TavilyResearchProvider(
            api_key="test-key",
            enable_network=True,
            http_get=http_get,
        ),
    )

    result = flow.search("https://example.com/exact-url")

    assert result.status == "ok"
    report_content = json.loads(flow.core.runtime.artifact_store.get_content(result.artifact_refs[1]))
    assert report_content["provider"] == "tavily"
    assert report_content["sources"][0]["title"] == "Exact URL Article"
    assert report_content["sources"][0]["url"] == "https://example.com/exact-url"
    assert "真实 URL 正文第一段" in report_content["report"]["summary"]
    assert "真实 URL 正文第二段" in report_content["report"]["claims"][0]["text"]


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


def test_research_flow_preserves_non_retryable_provider_readiness_check_trace(tmp_path):
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
    flow = ResearchFlow.in_process(tmp_path, provider=_TestProvider())

    result = flow.search("agent memory retrieval")
    record = flow.core.runtime.get_artifact_record(result.artifact_refs[1])

    assert record["artifact_type"] == "research.report"
    assert "Test summary for" in record["summary"]
    assert record["source_refs"] == [result.artifact_refs[0].to_dict()]
