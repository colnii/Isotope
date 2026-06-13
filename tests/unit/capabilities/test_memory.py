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

def test_memory_recall_capability_is_registered_as_inspection_product_candidate():
    runner = _runner()

    assert "memory.recall" in _ids(runner.list_capabilities())
    description = runner.describe_capability("memory.recall")
    assert description["shelf"] == "product_candidate"
    assert description["network_required"] is False
    assert description["input_contract"]["required"] == ["root", "query"]
    properties = description["input_contract"]["properties"]
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



def test_runner_discovers_memory_query_from_default_catalog():
    runner = _runner()

    assert "memory.query" in _ids(runner.list_capabilities())
    search = runner.search_capabilities(query="memory")

    assert "memory.query" in _ids(search["capabilities"])
    description = runner.describe_capability("memory.query")
    assert description["input_contract"]["required"] == ["root", "query", "run_id"]
    dense_properties = description["input_contract"]["properties"]["dense_retrieval"][
        "properties"
    ]
    assert dense_properties["backend"]["enum"] == ["local", "lancedb"]
    assert dense_properties["embedding_provider"]["enum"] == [
        "deterministic",
        "fastembed",
    ]
    assert "embedding_model" in dense_properties
    assert "path" in dense_properties
    assert "table_name" in dense_properties
    assert "memory_query_grant_gated" in description["safety_boundaries"]
    assert "memory_record_refs_expandable" in description["safety_boundaries"]



def test_runner_discovers_memory_promotion_preview_from_default_catalog():
    runner = _runner()

    assert "memory.promotion.preview" in _ids(runner.list_capabilities())
    search = runner.search_capabilities(query="promotion")

    assert "memory.promotion.preview" in _ids(search["capabilities"])
    description = runner.describe_capability("memory.promotion.preview")
    assert description["input_contract"]["required"] == [
        "run_id",
        "agent_id",
        "thread_id",
        "candidate",
    ]
    assert "write_memory_action_payload" in description["safety_boundaries"]
    assert "write_memory_action_handoff" in description["safety_boundaries"]



def test_memory_promotion_manifest_uses_action_handoff_language():
    description = _runner().describe_capability("memory.promotion.preview")
    manifest_text = json.dumps(description, ensure_ascii=False)
    forbidden_terms = [
        "proposal" + "_payload",
        "no" + "_memory" + "_write",
        "proposal" + "_only",
    ]

    assert "memory_promotion_projection" in description["safety_boundaries"]
    assert "write_memory_action_handoff" in description["safety_boundaries"]
    for term in forbidden_terms:
        assert term not in manifest_text



def test_memory_query_plan_stops_when_required_inputs_are_missing():
    plan = _runner().plan_capability_run(
        "memory.query",
        inputs={"root": "/tmp/isotope-runtime", "query": "memory boundary"},
    )

    assert plan["can_launch"] is False
    assert plan["status"] == "missing_inputs"
    assert plan["runner_kind"] == "deterministic_projection"
    assert plan["missing_inputs"] == ["run_id"]
    assert plan["scenario"] is None



def test_memory_promotion_preview_plan_stops_when_required_inputs_are_missing():
    plan = _runner().plan_capability_run(
        "memory.promotion.preview",
        inputs={
            "run_id": "run_memory",
            "agent_id": "agent_memo",
            "thread_id": "thread_memory",
        },
    )

    assert plan["can_launch"] is False
    assert plan["status"] == "missing_inputs"
    assert plan["runner_kind"] == "deterministic_projection"
    assert plan["missing_inputs"] == ["candidate"]
    assert plan["scenario"] is None





@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("root", 123),
        ("query", {"text": "memory"}),
        ("run_id", ["run_001"]),
        ("scope", "project"),
        ("limit", 0),
        ("controlled_expand", "yes"),
        ("expand_budget", True),
        ("dense_retrieval", "local"),
    ],
)
def test_memory_query_plan_rejects_invalid_inputs(field_name, bad_value):
    inputs = {
        "root": "/tmp/isotope-runtime",
        "query": "memory boundary",
        "run_id": "run_001",
    }
    inputs[field_name] = bad_value

    with pytest.raises(ValueError, match=field_name):
        _runner().plan_capability_run("memory.query", inputs=inputs)





@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("run_id", 123),
        ("agent_id", {"agent": "memo"}),
        ("thread_id", ["thread_memory"]),
        ("candidate", "raw text"),
        ("scope", "project"),
        ("quality", ""),
    ],
)
def test_memory_promotion_preview_plan_rejects_invalid_inputs(field_name, bad_value):
    inputs = {
        "run_id": "run_memory",
        "agent_id": "agent_memo",
        "thread_id": "thread_memory",
        "candidate": {
            "source_type": "artifact",
            "artifact_ref": {
                "ref_type": "artifact",
                "scope": "run",
                "run_id": "run_memory",
                "artifact_id": "artifact_report",
            },
            "artifact_type": "research.report",
            "summary": "Memory promotion preview.",
            "provenance": {"execution_id": "exec_report"},
        },
    }
    inputs[field_name] = bad_value

    with pytest.raises((TypeError, ValueError), match=field_name):
        _runner().plan_capability_run("memory.promotion.preview", inputs=inputs)



def test_memory_query_capability_runs_existing_public_metadata_query(tmp_path):
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    _write_memory_record(
        memory_dir,
        MemoryRecord(
            memory_id="mem_capability",
            scope="run",
            content={"raw": "raw memory content must not leak"},
            summary="Capability runner can recall memory boundaries.",
            source_refs=[{"ref_type": "artifact", "artifact_id": "artifact_memory"}],
            provenance={
                "run_id": "run_memory",
                "execution_id": "exec_memory",
                "action_type": "write_memory",
            },
            created_at="2026-05-27T00:00:00Z",
            supersedes=[],
            quality="verified",
        ),
    )

    result = _runner().run_capability(
        "memory.query",
        inputs={
            "root": str(tmp_path),
            "query": "memory boundaries",
            "run_id": "run_memory",
            "controlled_expand": True,
            "expand_budget": 100,
        },
    )

    assert result["kind"] == "capability_run_result"
    assert result["capability_id"] == "memory.query"
    assert result["status"] == "completed"
    assert result["runner_kind"] == "deterministic_projection"
    memory_query = result["memory_query"]
    assert memory_query["status"] == "ok"
    assert memory_query["content_policy"] == "memory_record_refs_expandable"
    assert memory_query["controlled_expand"]["status"] == "materialized"
    assert memory_query["controlled_expand"]["budget"] == 100
    assert memory_query["controlled_expand"]["content_policy"] == (
        "controlled_expand_memory_record_content_only"
    )
    assert memory_query["controlled_expand"]["materialized_results"] == [
        {
            "record_id": "mem_capability",
            "scope": "run",
            "encoding": "json",
            "materialized_text": '{"raw": "raw memory content must not leak"}',
            "used": memory_query["controlled_expand"]["used"],
            "truncated": False,
            "source_refs": [{"ref_type": "artifact", "artifact_id": "artifact_memory"}],
            "provenance": {
                "run_id": "run_memory",
                "execution_id": "exec_memory",
                "action_type": "write_memory",
            },
        }
    ]
    assert memory_query["results"] == [
        {
            "record_id": "mem_capability",
            "scope": "run",
            "summary": "Capability runner can recall memory boundaries.",
            "source_refs": [{"ref_type": "artifact", "artifact_id": "artifact_memory"}],
            "provenance": {
                "run_id": "run_memory",
                "execution_id": "exec_memory",
                "action_type": "write_memory",
            },
            "quality": "verified",
        }
    ]
    for mapping in _walk_mapping(result):
        assert FORBIDDEN_RESULT_KEYS.isdisjoint(mapping)


def test_memory_recall_capability_runs_state_root_preview_query(tmp_path):
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    _write_memory_record(
        memory_dir,
        MemoryRecord(
            memory_id="mem_recall",
            scope="run",
            content={"raw": "raw memory content must not leak"},
            summary="Capability runner can recall app-level memory previews.",
            source_refs=[{"ref_type": "artifact", "artifact_id": "artifact_memory"}],
            provenance={
                "run_id": "run_memory",
                "execution_id": "exec_memory",
                "action_type": "write_memory",
            },
            created_at="2026-06-04T00:00:00Z",
            supersedes=[],
            quality="verified",
        ),
    )

    result = _runner().run_capability(
        "memory.recall",
        inputs={
            "root": str(tmp_path),
            "query": "app-level memory previews",
            "scope": "run",
        },
    )

    assert result["kind"] == "capability_run_result"
    assert result["capability_id"] == "memory.recall"
    assert result["status"] == "completed"
    assert result["runner_kind"] == "deterministic_projection"
    recall = result["memory_recall"]
    assert recall["status"] == "ok"
    assert recall["content_policy"] == "memory_record_refs_expandable"
    assert recall["summary"]["matched"] == 1
    assert recall["results"] == [
        {
            "record_id": "mem_recall",
            "scope": "run",
            "summary": "Capability runner can recall app-level memory previews.",
            "source_refs": [{"ref_type": "artifact", "artifact_id": "artifact_memory"}],
            "provenance": {
                "run_id": "run_memory",
                "execution_id": "exec_memory",
                "action_type": "write_memory",
            },
            "quality": "verified",
        }
    ]
    for mapping in _walk_mapping(result):
        assert FORBIDDEN_RESULT_KEYS.isdisjoint(mapping)


def test_memory_promotion_preview_capability_returns_public_metadata_proposal():
    result = _runner().run_capability(
        "memory.promotion.preview",
        inputs={
            "run_id": "run_memory",
            "agent_id": "agent_memo",
            "thread_id": "thread_memory",
            "candidate": {
                "source_type": "artifact",
                "artifact_ref": {
                    "ref_type": "artifact",
                    "scope": "run",
                    "run_id": "run_memory",
                    "artifact_id": "artifact_report",
                },
                "artifact_type": "research.report",
                "summary": "Promote research report summary into memory.",
                "provenance": {"execution_id": "exec_report"},
            },
            "scope": "session",
            "quality": "verified",
        },
    )

    assert result["kind"] == "capability_run_result"
    assert result["capability_id"] == "memory.promotion.preview"
    assert result["status"] == "completed"
    assert result["runner_kind"] == "deterministic_projection"
    preview = result["memory_promotion_preview"]
    assert preview == {
        "action_type": "write_memory",
        "requested_capabilities": {"tools": ["write_memory"]},
        "scope": "session",
        "quality": "verified",
        "summary": "Promote research report summary into memory.",
        "source_refs": [
            {
                "ref_type": "artifact",
                "scope": "run",
                "run_id": "run_memory",
                "artifact_id": "artifact_report",
            }
        ],
        "provenance": {
            "promotion_source": "artifact",
            "source_execution_id": "exec_report",
        },
        "content_policy": "memory_record_refs_expandable",
    }
    output = json.dumps(result)
    assert "raw_content" not in output
    assert "raw memory content" not in output
    for mapping in _walk_mapping(result):
        assert FORBIDDEN_RESULT_KEYS.isdisjoint(mapping)
