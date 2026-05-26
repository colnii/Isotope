from __future__ import annotations

import json

import pytest

from isotope.features.research.providers import (
    CodexDelegatedResearchProvider,
    FakeResearchProvider,
    ResearchProviderError,
    build_codex_cli_research_backend,
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


def test_codex_delegated_provider_normalizes_common_codex_report_shape():
    raw_payload = {
        "research_id": "research_python_docs",
        "created_at": "2026-05-24T00:00:00Z",
        "status": "complete",
        "evidence_status": "source_backed_single_official_source",
        "sources": [
            {
                "source_id": "S1",
                "title": "Python documentation",
                "url": "https://docs.python.org/3/",
                "snippet": "Official Python documentation.",
                "why_used": "official source",
                "retrieved_at": "2026-05-24T00:00:00Z",
            }
        ],
        "report": [
            {
                "text": "Python docs are official.",
                "source_ids": ["S1"],
                "confidence": "high",
            }
        ],
    }

    provider = CodexDelegatedResearchProvider(backend=lambda prompt: json.dumps(raw_payload))

    payload = provider.run("python docs")

    assert payload["status"] == "ok"
    assert payload["evidence_status"] == "complete"
    assert payload["report"] == {
        "summary": "Python docs are official.",
        "claims": [
            {
                "text": "Python docs are official.",
                "source_ids": ["S1"],
                "confidence": "high",
            }
        ],
        "limitations": [],
        "next_queries": [],
    }


def test_codex_delegated_provider_retries_retryable_failure_once():
    calls = []

    def backend(prompt: str) -> str:
        calls.append(prompt)
        if len(calls) == 1:
            raise ResearchProviderError(
                "codex cli did not return an agent message: request timed out",
                details={
                    "codex_error_messages": ["Reconnecting... 2/5 (request timed out)"],
                    "codex_has_agent_message": False,
                },
            )
        return json.dumps(FakeResearchProvider().run("python docs"))

    provider = CodexDelegatedResearchProvider(backend=backend, max_attempts=2)

    payload = provider.run("python docs")

    assert len(calls) == 2
    assert payload["provider"] == "codex_delegated"
    assert payload["query"] == "python docs"


def test_codex_delegated_provider_records_attempts_when_retry_budget_exhausted():
    calls = []

    def backend(prompt: str) -> str:
        calls.append(prompt)
        raise ResearchProviderError(
            "codex cli did not return an agent message: request timed out",
            details={
                "codex_error_messages": [f"request timed out on attempt {len(calls)}"],
                "codex_timeout_seconds": 60,
            },
        )

    provider = CodexDelegatedResearchProvider(backend=backend, max_attempts=2)

    with pytest.raises(ResearchProviderError) as exc_info:
        provider.run("python docs")

    assert len(calls) == 2
    assert exc_info.value.details["attempt_count"] == 2
    assert exc_info.value.details["retry_exhausted"] is True
    assert exc_info.value.details["attempts"] == [
        {
            "attempt": 1,
            "message": "codex cli did not return an agent message: request timed out",
            "retryable": True,
            "details": {
                "codex_error_messages": ["request timed out on attempt 1"],
                "codex_timeout_seconds": 60,
            },
        },
        {
            "attempt": 2,
            "message": "codex cli did not return an agent message: request timed out",
            "retryable": True,
            "details": {
                "codex_error_messages": ["request timed out on attempt 2"],
                "codex_timeout_seconds": 60,
            },
        },
    ]


def test_build_codex_cli_research_backend_returns_callable(tmp_path):
    backend = build_codex_cli_research_backend(
        workspace_root=tmp_path,
        executable="codex",
        executable_resolver=lambda name: "/usr/bin/codex",
        process_runner=lambda *args, **kwargs: type(
            "Completed",
            (),
            {
                "stdout": '{"sources":[],"report":{"summary":"empty"}}',
                "stderr": "",
                "returncode": 0,
            },
        )(),
    )

    assert callable(backend)
    assert json.loads(backend("research prompt")) == {
        "sources": [],
        "report": {"summary": "empty"},
    }


def test_codex_cli_research_backend_extracts_agent_message_from_jsonl(tmp_path):
    stdout = "\n".join(
        [
            '{"type":"thread.started","thread_id":"thread_001"}',
            '{"type":"turn.started"}',
            '{"type":"item.completed","item":{"id":"item_1","type":"agent_message","text":"{\\"status\\":\\"ok\\",\\"sources\\":[],\\"report\\":{\\"summary\\":\\"debug\\"}}"}}',
            '{"type":"turn.completed"}',
        ]
    )
    backend = build_codex_cli_research_backend(
        workspace_root=tmp_path,
        executable="codex",
        executable_resolver=lambda name: "/usr/bin/codex",
        process_runner=lambda *args, **kwargs: type(
            "Completed",
            (),
            {"stdout": stdout, "stderr": "", "returncode": 0},
        )(),
    )

    assert json.loads(backend("research prompt")) == {
        "status": "ok",
        "sources": [],
        "report": {"summary": "debug"},
    }


def test_codex_cli_research_backend_rejects_error_only_jsonl(tmp_path):
    stdout = "\n".join(
        [
            '{"type":"thread.started","thread_id":"thread_001"}',
            '{"type":"error","message":"Reconnecting... 2/5 (request timed out)"}',
            '{"type":"error","message":"stream disconnected before final answer"}',
        ]
    )
    backend = build_codex_cli_research_backend(
        workspace_root=tmp_path,
        executable="codex",
        executable_resolver=lambda name: "/usr/bin/codex",
        process_runner=lambda *args, **kwargs: type(
            "Completed",
            (),
            {"stdout": stdout, "stderr": "", "returncode": 0},
        )(),
    )

    with pytest.raises(ResearchProviderError, match="codex cli did not return an agent message") as exc_info:
        backend("research prompt")

    assert exc_info.value.details == {
        "codex_event_counts": {
            "error": 2,
            "thread.started": 1,
        },
        "codex_error_messages": [
            "Reconnecting... 2/5 (request timed out)",
            "stream disconnected before final answer",
        ],
        "codex_has_agent_message": False,
        "codex_timeout_seconds": 120,
    }
