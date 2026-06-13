from __future__ import annotations

import importlib
import json
from dataclasses import asdict

from isotope.capabilities.catalog import CapabilityCatalog
from isotope.platform.schemas.memory import MemoryRecord


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


def _walk_mapping(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_mapping(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_mapping(child)


def _write_memory_record(memory_dir, record):
    (memory_dir / f"{record.memory_id}.json").write_text(
        json.dumps(asdict(record), sort_keys=True),
        encoding="utf-8",
    )


def test_memory_query_capability_runner_accepts_local_dense_retrieval(tmp_path):
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    _write_memory_record(
        memory_dir,
        MemoryRecord(
            memory_id="mem_dense_capability",
            scope="run",
            content={"raw": "raw memory content must not leak"},
            summary="Capability runner can recall dense memory boundaries.",
            source_refs=[{"ref_type": "artifact", "artifact_id": "artifact_memory"}],
            provenance={
                "run_id": "run_memory",
                "execution_id": "exec_memory",
                "action_type": "write_memory",
            },
            created_at="2026-06-14T00:00:00Z",
            supersedes=[],
            quality="verified",
        ),
    )

    result = _runner().run_capability(
        "memory.query",
        inputs={
            "root": str(tmp_path),
            "query": "dense memory boundaries",
            "run_id": "run_memory",
            "dense_retrieval": {"backend": "local", "dimensions": 8},
        },
    )

    memory_query = result["memory_query"]
    assert memory_query["retrieval"] == {"backend": "hybrid", "dense_status": "ok"}
    assert memory_query["results"] == [
        {
            "record_id": "mem_dense_capability",
            "scope": "run",
            "summary": "Capability runner can recall dense memory boundaries.",
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


def test_memory_recall_capability_accepts_local_dense_retrieval(tmp_path):
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    _write_memory_record(
        memory_dir,
        MemoryRecord(
            memory_id="mem_recall_dense",
            scope="run",
            content={"raw": "raw memory content must not leak"},
            summary="App-level dense memory preview.",
            source_refs=[{"ref_type": "artifact", "artifact_id": "artifact_memory"}],
            provenance={
                "run_id": "run_memory",
                "execution_id": "exec_memory",
                "action_type": "write_memory",
            },
            created_at="2026-06-14T00:00:00Z",
            supersedes=[],
            quality="verified",
        ),
    )

    result = _runner().run_capability(
        "memory.recall",
        inputs={
            "root": str(tmp_path),
            "query": "dense memory preview",
            "scope": "run",
            "dense_retrieval": {"backend": "local", "dimensions": 8},
        },
    )

    recall = result["memory_recall"]
    assert recall["retrieval"] == {"backend": "hybrid", "dense_status": "ok"}
    assert recall["results"] == [
        {
            "record_id": "mem_recall_dense",
            "scope": "run",
            "summary": "App-level dense memory preview.",
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
