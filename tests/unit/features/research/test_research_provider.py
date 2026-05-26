from __future__ import annotations

import json

import pytest

from isotope.features.research.providers import (
    CodexDelegatedResearchProvider,
    FakeResearchProvider,
    ResearchProviderError,
    build_research_provider,
    build_codex_cli_research_backend,
    extract_research_json,
    get_research_provider_descriptor,
    list_research_provider_descriptors,
    tavily_api_key_from_config,
)
from isotope.features.research.tavily import TavilyResearchProvider


def test_fake_research_provider_returns_source_backed_report():
    provider = FakeResearchProvider()

    payload = provider.run("agent memory retrieval")

    assert payload["query"] == "agent memory retrieval"
    assert payload["provider"] == "fake"
    assert payload["sources"][0]["source_id"] == "src_001"
    assert payload["report"]["claims"][0]["source_ids"] == ["src_001"]


def test_research_provider_registry_lists_implemented_and_planned_providers():
    descriptors = list_research_provider_descriptors()

    assert [descriptor.provider_id for descriptor in descriptors] == [
        "fake",
        "codex",
        "tavily",
        "searxng",
        "browser",
    ]
    assert get_research_provider_descriptor("fake").implemented is True
    assert get_research_provider_descriptor("codex").provider_name == "codex_delegated"
    assert get_research_provider_descriptor("tavily").implemented is True
    assert get_research_provider_descriptor("tavily").selectable is True


def test_build_research_provider_reuses_fake_provider():
    provider = build_research_provider("fake")

    assert isinstance(provider, FakeResearchProvider)
    assert provider.provider_name == "fake"


def test_build_research_provider_reuses_tavily_preflight_provider(tmp_path):
    provider = build_research_provider(
        "tavily",
        tavily_api_key="test-key",
        tavily_enable_network=True,
        tavily_timeout_seconds=9,
        tavily_max_results=3,
    )

    assert type(provider).__name__ == "TavilyResearchProvider"
    assert provider.provider_name == "tavily"
    assert provider.enable_network is True
    assert provider.timeout_seconds == 9
    assert provider.max_results == 3


def test_tavily_api_key_from_config_reads_plaintext_local_toml(tmp_path):
    config_path = tmp_path / "research_tavily.toml"
    config_path.write_text('api_key = "test-secret-key"\n', encoding="utf-8")

    assert tavily_api_key_from_config(config_path) == "test-secret-key"


def test_tavily_api_key_from_config_reads_environment_reference(tmp_path, monkeypatch):
    config_path = tmp_path / "research_tavily.toml"
    config_path.write_text('api_key = "env:LOCAL_TAVILY_KEY"\n', encoding="utf-8")
    monkeypatch.setenv("LOCAL_TAVILY_KEY", "test-env-secret")

    assert tavily_api_key_from_config(config_path) == "test-env-secret"


def test_build_research_provider_uses_tavily_config_when_no_direct_key(
    tmp_path,
    monkeypatch,
):
    config_path = tmp_path / "research_tavily.toml"
    config_path.write_text('api_key = "test-secret-key"\n', encoding="utf-8")
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    provider = build_research_provider(
        "tavily",
        tavily_config_path=config_path,
    )

    with pytest.raises(ResearchProviderError) as exc_info:
        provider.run("agent memory retrieval")
    assert exc_info.value.details["error_code"] == "network_execution_deferred"
    assert "test-secret-key" not in json.dumps(exc_info.value.details)


def test_tavily_preflight_provider_reports_missing_api_key_as_non_retryable():
    provider = TavilyResearchProvider(api_key=None)

    with pytest.raises(ResearchProviderError) as exc_info:
        provider.run("agent memory retrieval")

    assert str(exc_info.value) == "tavily provider requires TAVILY_API_KEY"
    assert exc_info.value.details == {
        "provider_id": "tavily",
        "error_code": "missing_api_key",
        "required_env": "TAVILY_API_KEY",
        "retryable": False,
    }


def test_tavily_preflight_provider_reports_deferred_network_execution():
    provider = TavilyResearchProvider(
        api_key="test-key",
        enable_network=False,
        timeout_seconds=7,
        max_results=3,
    )

    with pytest.raises(ResearchProviderError) as exc_info:
        provider.run("agent memory retrieval")

    assert "preflight only" in str(exc_info.value)
    assert exc_info.value.details == {
        "provider_id": "tavily",
        "error_code": "network_execution_deferred",
        "api_key_configured": True,
        "timeout_seconds": 7,
        "max_results": 3,
        "retryable": False,
    }


def test_tavily_provider_executes_search_with_injected_http_backend():
    calls = []

    def http_post(url, *, headers, payload, timeout_seconds):
        calls.append(
            {
                "url": url,
                "headers": headers,
                "payload": payload,
                "timeout_seconds": timeout_seconds,
            }
        )
        return {
            "query": "agent memory retrieval",
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

    provider = TavilyResearchProvider(
        api_key="test-secret-key",
        enable_network=True,
        timeout_seconds=9,
        max_results=3,
        http_post=http_post,
    )

    payload = provider.run("agent memory retrieval")

    assert calls == [
        {
            "url": "https://api.tavily.com/search",
            "headers": {
                "Authorization": "Bearer test-secret-key",
                "Content-Type": "application/json",
            },
            "payload": {
                "query": "agent memory retrieval",
                "search_depth": "basic",
                "max_results": 3,
                "include_answer": False,
                "include_raw_content": False,
                "include_usage": True,
            },
            "timeout_seconds": 9,
        }
    ]
    assert payload["status"] == "ok"
    assert payload["provider"] == "tavily"
    assert payload["sources"] == [
        {
            "source_id": "src_001",
            "title": "Isotope research note",
            "url": "https://example.com/research-note",
            "snippet": "Research claims should cite source-backed snippets.",
            "why_used": "Tavily search result rank 1, score 0.91",
            "retrieved_at": payload["sources"][0]["retrieved_at"],
            "provider_rank": 1,
        }
    ]
    assert payload["report"]["claims"][0]["source_ids"] == ["src_001"]
    assert payload["provenance"]["tavily"]["response_time"] == 0.42
    assert payload["provenance"]["tavily"]["usage"] == {"credits": 1}
    assert "test-secret-key" not in json.dumps(payload)


def test_build_research_provider_rejects_unknown_provider():
    with pytest.raises(ValueError, match="unknown research provider"):
        build_research_provider("missing")


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
