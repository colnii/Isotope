"""Memory developer demo scenarios."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .memory.views import build_memory_query_payload
from .platform.schemas.memory import MemoryRecord
from .platform.state.memory_store import FileMemoryStore


def _run_memory_query_smoke_demo(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    store = FileMemoryStore(root)
    record = MemoryRecord(
        memory_id="mem_demo_query",
        scope="run",
        content={"raw": "raw memory content must not leak"},
        summary="Resume from the memory query smoke boundary.",
        source_refs=[{"ref_type": "artifact", "artifact_id": "artifact_demo_query"}],
        provenance={
            "run_id": "run_demo_query",
            "execution_id": "exec_demo_query",
            "action_type": "write_memory",
        },
        created_at="2026-05-24T00:00:00Z",
        supersedes=[],
        quality="candidate",
    )
    store.append_record(record)

    query_payload = build_memory_query_payload(
        root=root,
        query="query smoke",
        run_id="run_demo_query",
        limit=5,
    )
    results = query_payload["results"]
    recalled = results[0] if results else {}
    memory_query_smoke_ok = (
        query_payload["status"] == "ok"
        and len(results) == 1
        and recalled.get("record_id") == record.memory_id
        and "content" not in recalled
    )

    return {
        "scenario": "memory-query-smoke",
        "transport": "in_process",
        "memory_write_status": "saved",
        "memory_query_status": query_payload["status"],
        "memory_query_smoke_ok": memory_query_smoke_ok,
        "query": query_payload["query"],
        "query_result_count": len(results),
        "recalled_record": recalled,
        "recalled_record_id": recalled.get("record_id"),
        "content_policy": "summary_refs_provenance_only",
        "model_status": "not_used",
        "provider_status": "not_used",
        "network_listener_status": "not_used",
        "next_development_step": "add memory query route only after expand policy is explicit",
    }
