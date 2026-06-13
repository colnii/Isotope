from __future__ import annotations

import importlib
import json

from isotope.capabilities.catalog import CapabilityCatalog
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


def _runner():
    return _runner_module().CapabilityRunner(catalog=CapabilityCatalog.default())


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


def test_runner_discovers_research_recall_from_default_catalog():
    runner = _runner()

    assert "research.recall" in _ids(runner.list_capabilities())
    search = runner.search_capabilities(query="research recall")

    assert _ids(search["capabilities"]) == ["research.recall"]
    description = runner.describe_capability("research.recall")
    assert description["input_contract"]["required"] == ["root", "query"]
    properties = description["input_contract"]["properties"]
    assert set(properties) == {"root", "query", "run_id", "limit", "dense_retrieval"}
    assert properties["root"]["x-system-input"] is True
    dense_properties = properties["dense_retrieval"]["properties"]
    assert dense_properties["backend"]["enum"] == ["local", "lancedb"]
    assert dense_properties["embedding_provider"]["enum"] == [
        "deterministic",
        "fastembed",
    ]
    assert "embedding_model" in dense_properties
    assert "path" in dense_properties
    assert "table_name" in dense_properties
    assert "research_report_artifact_preview_only" in description["safety_boundaries"]
    assert "no_research_artifact_content_return" in description["safety_boundaries"]
    assert (
        "report_content_via_artifact_inspect" in description["safety_boundaries"]
    )
    assert "artifact inspect" in description["description"]


def test_research_recall_plan_is_launchable_with_root_and_query():
    plan = _runner().plan_capability_run(
        "research.recall",
        inputs={
            "root": "/tmp/isotope-runtime",
            "query": "artifact preview recall",
        },
    )

    assert plan["can_launch"] is True
    assert plan["status"] == "launchable"
    assert plan["missing_inputs"] == []


def test_research_recall_capability_returns_preview_without_content(tmp_path):
    store = ArtifactStore(tmp_path)
    report = store.create_artifact(
        "run_research",
        execution_id="exec_research",
        artifact_type="research.report",
        summary="Capability recall preview for generic RAG index.",
        content=json.dumps(
            {"body": "raw report content must not leak through capability"},
            sort_keys=True,
        ),
        source_refs=[{"ref_type": "url", "url": "https://example.com/capability"}],
    )

    result = _runner().run_capability(
        "research.recall",
        inputs={
            "root": str(tmp_path),
            "query": "generic RAG index",
            "dense_retrieval": {"backend": "local", "dimensions": 8},
        },
    )

    assert result["kind"] == "capability_run_result"
    assert result["capability_id"] == "research.recall"
    assert result["status"] == "completed"
    assert result["runner_kind"] == "deterministic_projection"
    recall = result["research_recall"]
    assert recall["content_policy"] == "research_report_artifact_preview_only"
    assert recall["retrieval"] == {"backend": "hybrid", "dense_status": "ok"}
    assert recall["results"] == [
        {
            "run_id": "run_research",
            "artifact_id": report.artifact_id,
            "artifact_type": "research.report",
            "summary": "Capability recall preview for generic RAG index.",
            "ref": report.ref.to_dict(),
            "source_refs": [
                {"ref_type": "url", "url": "https://example.com/capability"}
            ],
            "provenance": {"execution_id": "exec_research"},
        }
    ]
    encoded = json.dumps(result, ensure_ascii=False, sort_keys=True)
    assert "raw report content must not leak" not in encoded
    for mapping in _walk_mapping(result):
        assert FORBIDDEN_RESULT_KEYS.isdisjoint(mapping)
