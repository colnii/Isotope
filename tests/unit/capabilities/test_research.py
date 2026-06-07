import importlib
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

from isotope.capabilities.catalog import Capability, CapabilityCatalog
from isotope.features.supervisor.registry import (
    ManagedCodexRecord,
    append_managed_record,
    default_registry_path,
)
from isotope.platform.schemas.memory import MemoryRecord
from isotope.workspace.artifacts import ArtifactStore


FORBIDDEN_RESULT_KEYS = {
    "api_key",
    "content",
    "full_content",
    "local_path",
    "prompt",
    "raw_content",
    "transcript",
}


def _runner_module():
    return importlib.import_module("isotope.capabilities.runner")


def _runner(*, catalog=None):
    return _runner_module().CapabilityRunner(
        catalog=catalog or CapabilityCatalog.default()
    )


def _ids(entries):
    return [entry["capability_id"] for entry in entries]


def _walk_mapping(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_mapping(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_mapping(child)


def _write_memory_record(memory_dir, record):
    from dataclasses import asdict
    (memory_dir / f"{record.memory_id}.json").write_text(
        json.dumps(asdict(record), sort_keys=True),
        encoding="utf-8",
    )


def _capability(capability_id, shelf, **overrides):
    data = {
        "capability_id": capability_id,
        "title": capability_id.replace(".", " ").title(),
        "description": f"{capability_id} capability metadata.",
        "maturity": "v0.2",
        "shelf": shelf,
        "domain_tags": tuple(capability_id.split(".")),
        "input_contract": {"type": "object"},
        "output_contract": {"type": "object"},
        "safety_boundaries": ("public_metadata_manifest_only",),
        "default_enabled": True,
        "required_env": (),
        "network_required": False,
        "provider": None,
        "model": None,
    }
    data.update(overrides)
    return Capability(**data)

def test_runner_discovers_research_search_from_default_catalog():
    runner = _runner()

    assert "research.search" in _ids(runner.list_capabilities())
    search = runner.search_capabilities(query="research search")

    assert _ids(search["capabilities"]) == ["research.search"]
    description = runner.describe_capability("research.search")
    assert description["input_contract"]["required"] == [
        "root",
        "query",
    ]
    properties = description["input_contract"]["properties"]
    assert set(properties) == {
        "root",
        "query",
        "provider",
        "allow_network",
        "tavily_max_results",
    }
    assert properties["provider"]["x-system-input"] is True
    assert properties["allow_network"]["x-system-input"] is True
    assert properties["tavily_max_results"]["x-system-input"] is True
    assert "reuses_research_flow" in description["safety_boundaries"]
    assert "runtime_provider_policy" in description["safety_boundaries"]



def test_runner_discovers_research_promote_from_default_catalog():
    runner = _runner()

    assert "research.promote" in _ids(runner.list_capabilities())
    search = runner.search_capabilities(query="research promote")

    assert _ids(search["capabilities"]) == ["research.promote"]
    description = runner.describe_capability("research.promote")
    assert description["input_contract"]["required"] == [
        "root",
        "run_id",
        "artifact_id",
        "agent_id",
        "thread_id",
    ]
    assert description["input_contract"]["properties"]["scope"]["enum"] == [
        "thread",
        "run",
        "session",
    ]
    assert "reuses_memory_promotion_boundary" in description["safety_boundaries"]
    assert "write_memory_action_handoff" in description["safety_boundaries"]



def test_research_promote_manifest_uses_memory_handoff_language():
    description = _runner().describe_capability("research.promote")
    manifest_text = json.dumps(description, ensure_ascii=False)
    forbidden_terms = [
        "proposal" + "_only",
        "no" + "_memory" + "_write",
        "no" + "_proposal" + "_payload",
    ]

    assert "research_promotion_projection" in description["safety_boundaries"]
    assert "write_memory_action_handoff" in description["safety_boundaries"]
    for term in forbidden_terms:
        assert term not in manifest_text



def test_research_search_plan_is_launchable_with_runtime_provider_policy():
    plan = _runner().plan_capability_run(
        "research.search",
        inputs={
            "root": "/tmp/isotope-runtime",
            "query": "capacity research integration",
        },
    )

    assert plan["can_launch"] is True
    assert plan["status"] == "launchable"
    assert plan["missing_inputs"] == []



def test_research_search_uses_runtime_provider_policy_by_default(
    tmp_path, monkeypatch
):
    from isotope.capabilities import research as research_capability

    calls = []

    class RecordingCodexProvider:
        provider_name = "codex_delegated"

        def run(self, query):
            return {
                "research_id": "research_codex_unit",
                "query": query,
                "provider": "codex_delegated",
                "created_at": "2026-06-03T00:00:00Z",
                "status": "ok",
                "evidence_status": "complete",
                "sources": [
                    {
                        "source_id": "src_001",
                        "title": "Isotope research note",
                        "url": "https://example.com/isotope-research",
                        "snippet": "Research claims should cite source ids.",
                        "why_used": "unit test Codex provider",
                        "retrieved_at": "2026-06-03T00:00:00Z",
                    }
                ],
                "report": {
                    "summary": "Codex research summary for capacity research integration.",
                    "claims": [
                        {
                            "text": "Research claims should cite source ids.",
                            "source_ids": ["src_001"],
                            "confidence": "medium",
                        }
                    ],
                    "limitations": [],
                    "next_queries": [],
                },
                "provenance": {"provider": "codex_delegated"},
            }

    def build_provider(provider_id, **kwargs):
        calls.append({"provider_id": provider_id, **kwargs})
        return RecordingCodexProvider()

    monkeypatch.setattr(
        research_capability,
        "build_research_provider",
        build_provider,
    )

    result = _runner().run_capability(
        "research.search",
        inputs={
            "root": str(tmp_path),
            "query": "capacity research integration",
        },
    )

    assert result["kind"] == "capability_run_result"
    assert result["capability_id"] == "research.search"
    assert result["status"] == "completed"
    assert result["runner_kind"] == "deterministic_local"
    research_search = result["research_search"]
    assert research_search["status"] == "ok"
    assert research_search["query"] == "capacity research integration"
    assert research_search["provider"] == "codex_delegated"
    assert research_search["evidence_status"] == "complete"
    assert research_search["source_count"] == 1
    assert calls == [{"provider_id": "codex", "workspace_root": str(tmp_path)}]
    assert (
        research_search["report_summary"]
        == "Codex research summary for capacity research integration."
    )
    assert research_search["content_status"] == "source_preview"
    assert (
        research_search["content_note"]
        == "Research result contains source-backed previews, not full article text."
    )
    assert research_search["source_previews"] == [
        {
            "source_id": "src_001",
            "title": "Isotope research note",
            "url": "https://example.com/isotope-research",
            "snippet": "Research claims should cite source ids.",
            "why_used": "unit test Codex provider",
        }
    ]
    assert [item["artifact_type"] for item in research_search["artifacts"]] == [
        "research.raw_transcript",
        "research.report",
    ]
    assert "research" not in result
    for mapping in _walk_mapping(result):
        assert FORBIDDEN_RESULT_KEYS.isdisjoint(mapping)



def test_research_search_private_tavily_policy_uses_research_flow_artifacts(
    tmp_path, monkeypatch
):
    from isotope.capabilities import research as research_capability

    calls = []

    class RecordingTavilyProvider:
        provider_name = "tavily"

        def run(self, query):
            return {
                "research_id": "research_tavily_unit",
                "query": query,
                "provider": "tavily",
                "created_at": "2026-06-03T00:00:00Z",
                "status": "ok",
                "evidence_status": "complete",
                "sources": [
                    {
                        "source_id": "src_001",
                        "title": "Isotope research note",
                        "url": "https://example.com/research-note",
                        "snippet": "Research claims should cite source-backed snippets.",
                        "why_used": "unit test Tavily provider",
                        "retrieved_at": "2026-06-03T00:00:00Z",
                    }
                ],
                "report": {
                    "summary": "Tavily research summary.",
                    "claims": [
                        {
                            "text": "Research claims should cite source-backed snippets.",
                            "source_ids": ["src_001"],
                            "confidence": "medium",
                        }
                    ],
                    "limitations": [],
                    "next_queries": [],
                },
                "provenance": {"provider": "tavily"},
            }

    def build_provider(provider_id, **kwargs):
        calls.append({"provider_id": provider_id, **kwargs})
        return RecordingTavilyProvider()

    monkeypatch.setattr(
        research_capability,
        "build_research_provider",
        build_provider,
    )

    result = research_capability.run_research_search(
        inputs={
            "root": str(tmp_path),
            "query": "capacity research integration",
            "provider": "tavily",
            "allow_network": True,
            "tavily_max_results": 3,
        },
    )

    assert calls == [
        {
            "provider_id": "tavily",
            "workspace_root": str(tmp_path),
            "tavily_enable_network": True,
            "tavily_max_results": 3,
        }
    ]
    research_search = result["research_search"]
    assert research_search["provider"] == "tavily"
    assert research_search["source_count"] == 1
    assert research_search["content_status"] == "source_preview"
    assert "source-backed previews" in research_search["content_note"]
    assert [item["artifact_type"] for item in research_search["artifacts"]] == [
        "research.raw_transcript",
        "research.report",
    ]
    for mapping in _walk_mapping(result):
        assert FORBIDDEN_RESULT_KEYS.isdisjoint(mapping)



def test_research_search_tavily_exact_url_returns_extract_summary(
    tmp_path, monkeypatch
):
    from isotope.capabilities import research as research_capability

    class ExactUrlTavilyProvider:
        provider_name = "tavily"

        def run(self, query):
            return {
                "research_id": "research_exact_url_unit",
                "query": query,
                "provider": "tavily",
                "created_at": "2026-06-03T00:00:00Z",
                "status": "ok",
                "evidence_status": "complete",
                "sources": [
                    {
                        "source_id": "src_001",
                        "title": "Exact URL Article",
                        "url": query,
                        "snippet": "真实 URL 正文片段，可直接用于总结。",
                        "why_used": "Exact URL content fetched for the user-provided URL.",
                        "retrieved_at": "2026-06-03T00:00:00Z",
                        "provider_rank": 1,
                    }
                ],
                "report": {
                    "summary": "真实 URL 正文摘要，包含页面实际内容。",
                    "claims": [
                        {
                            "text": "真实 URL 正文片段，可直接用于总结。",
                            "source_ids": ["src_001"],
                            "confidence": "medium",
                        }
                    ],
                    "limitations": [],
                    "next_queries": [],
                },
                "provenance": {"provider": "tavily", "tavily": {"mode": "exact_url_fetch"}},
            }

    monkeypatch.setattr(
        research_capability,
        "build_research_provider",
        lambda provider_id, **kwargs: ExactUrlTavilyProvider(),
    )

    result = research_capability.run_research_search(
        inputs={
            "root": str(tmp_path),
            "query": "https://example.com/exact-url",
            "provider": "tavily",
            "allow_network": True,
        },
    )

    research_search = result["research_search"]
    assert research_search["provider"] == "tavily"
    assert research_search["report_summary"] == "真实 URL 正文摘要，包含页面实际内容。"
    assert research_search["source_previews"] == [
        {
            "source_id": "src_001",
            "title": "Exact URL Article",
            "url": "https://example.com/exact-url",
            "snippet": "真实 URL 正文片段，可直接用于总结。",
            "why_used": "Exact URL content fetched for the user-provided URL.",
            "provider_rank": 1,
        }
    ]
    assert "raw_content" not in json.dumps(result, ensure_ascii=False)



def test_research_search_default_policy_uses_research_flow_artifacts(
    tmp_path, monkeypatch
):
    from isotope.capabilities import research as research_capability

    calls = []

    class RecordingCodexProvider:
        provider_name = "codex_delegated"

        def run(self, query):
            return {
                "research_id": "research_codex_unit",
                "query": query,
                "provider": "codex_delegated",
                "created_at": "2026-06-03T00:00:00Z",
                "status": "ok",
                "evidence_status": "complete",
                "sources": [
                    {
                        "source_id": "src_001",
                        "title": "Codex delegated source",
                        "url": "https://example.com/codex-source",
                        "snippet": "Codex delegated research returns cited snippets.",
                        "why_used": "unit test Codex provider",
                        "retrieved_at": "2026-06-03T00:00:00Z",
                    }
                ],
                "report": {
                    "summary": "Codex delegated research summary.",
                    "claims": [
                        {
                            "text": "Codex delegated research returns cited snippets.",
                            "source_ids": ["src_001"],
                            "confidence": "medium",
                        }
                    ],
                    "limitations": [],
                    "next_queries": [],
                },
                "provenance": {"provider": "codex_delegated"},
            }

    def build_provider(provider_id, **kwargs):
        calls.append({"provider_id": provider_id, **kwargs})
        return RecordingCodexProvider()

    monkeypatch.setattr(
        research_capability,
        "build_research_provider",
        build_provider,
    )

    result = _runner().run_capability(
        "research.search",
        inputs={
            "root": str(tmp_path),
            "query": "capacity research integration",
        },
    )

    assert calls == [
        {
            "provider_id": "codex",
            "workspace_root": str(tmp_path),
        }
    ]
    research_search = result["research_search"]
    assert research_search["provider"] == "codex_delegated"
    assert research_search["source_count"] == 1
    assert [item["artifact_type"] for item in research_search["artifacts"]] == [
        "research.raw_transcript",
        "research.report",
    ]
    for mapping in _walk_mapping(result):
        assert FORBIDDEN_RESULT_KEYS.isdisjoint(mapping)



def test_research_promote_capability_builds_public_metadata_proposal_summary(tmp_path):
    store = ArtifactStore(tmp_path)
    artifact = store.create_artifact(
        "run_research",
        execution_id="exec_research",
        artifact_type="research.report",
        summary="Stub research summary for capacity promotion.",
        content=json.dumps(
            {
                "evidence_status": "complete",
                "sources": [{"source_id": "src_001", "title": "Source"}],
                "report": {
                    "summary": "raw report body must not leak through capability",
                    "claims": [
                        {"text": "Source-backed claim.", "source_ids": ["src_001"]}
                    ],
                },
            },
            sort_keys=True,
        ),
    )

    result = _runner().run_capability(
        "research.promote",
        inputs={
            "root": str(tmp_path),
            "run_id": "run_research",
            "artifact_id": artifact.artifact_id,
            "agent_id": "agent_capacity",
            "thread_id": "thread_capacity",
            "scope": "session",
            "quality": "candidate",
            "proposal_id": "prop_capacity_research",
        },
    )

    assert result["kind"] == "capability_run_result"
    assert result["capability_id"] == "research.promote"
    assert result["status"] == "completed"
    assert result["runner_kind"] == "deterministic_local"
    promotion = result["research_promotion"]
    assert promotion == {
        "status": "ok",
        "artifact_type": "research.report",
        "artifact_ref": artifact.ref.to_dict(),
        "proposal_id": "prop_capacity_research",
        "action_type": "write_memory",
        "scope": "session",
        "quality": "candidate",
        "summary": "Stub research summary for capacity promotion.",
        "source_refs": [artifact.ref.to_dict()],
        "requested_capabilities": {"tools": ["write_memory"]},
        "quality_gate_status": "promotable",
        "quality_gate_reasons": [],
        "memory_write": "write_memory_action_handoff",
    }
    output = json.dumps(result, sort_keys=True)
    assert "raw report body" not in output
    for mapping in _walk_mapping(result):
        assert FORBIDDEN_RESULT_KEYS.isdisjoint(mapping)


