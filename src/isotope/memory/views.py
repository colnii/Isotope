"""Read-only memory projections for worker and memory status views."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from isotope.platform.schemas.memory import MemoryRecord
from isotope.platform.state.memory_store import FileMemoryStore
from isotope.platform.state.multi_worker import (
    build_multi_worker_status_payload,
    render_multi_worker_status_plain,
)


VALID_SCOPES = ("thread", "run", "session")


def build_memory_status_payload(
    *,
    root: Path | str,
    scope: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    root_path = Path(root).expanduser()
    if scope is not None and scope not in VALID_SCOPES:
        raise ValueError("memory scope must be thread, run, or session")
    if limit <= 0:
        raise ValueError("limit must be positive")

    records = FileMemoryStore(root_path).list_records(scope=scope)
    sorted_records = sorted(
        records,
        key=lambda record: (record.created_at, record.memory_id),
        reverse=True,
    )
    visible = sorted_records[:limit]
    by_scope = Counter(record.scope for record in records)
    by_quality = Counter(record.quality for record in records)
    return {
        "status": "ok",
        "store": {
            "root": str(root_path),
            "path": str(root_path / "memory"),
            "format": "file_memory_store",
        },
        "scope": scope,
        "summary": {
            "total": len(records),
            "by_scope": {scope_name: by_scope.get(scope_name, 0) for scope_name in VALID_SCOPES},
            "by_quality": dict(sorted(by_quality.items())),
            "hidden_records": max(0, len(records) - len(visible)),
        },
        "records": [_memory_record_preview(record) for record in visible],
    }


def build_memory_query_payload(
    *,
    root: Path | str,
    query: str,
    scope: str | None = None,
    run_id: str | None = None,
    session_id: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    root_path = Path(root).expanduser()
    if scope is not None and scope not in VALID_SCOPES:
        raise ValueError("memory scope must be thread, run, or session")
    if limit <= 0:
        raise ValueError("limit must be positive")
    clean_query = _required_query(query)

    records = FileMemoryStore(root_path).list_records(scope=scope)
    matched = query_memory_records(
        records,
        query=clean_query,
        run_id=run_id,
        session_id=session_id,
        limit=limit,
    )
    return {
        "status": "ok",
        "store": {
            "root": str(root_path),
            "path": str(root_path / "memory"),
            "format": "file_memory_store",
        },
        "query": clean_query,
        "scope": scope,
        "run_id": run_id,
        "session_id": session_id,
        "summary": {
            "total": len(records),
            "matched": len(matched.all_matches),
            "hidden_records": max(0, len(matched.all_matches) - len(matched.visible)),
        },
        "results": [_memory_query_result(record) for record in matched.visible],
    }


def query_memory_records(
    records: list[MemoryRecord],
    *,
    query: str,
    run_id: str | None = None,
    session_id: str | None = None,
    limit: int = 20,
) -> "_MemoryQueryMatches":
    if limit <= 0:
        raise ValueError("limit must be positive")
    clean_query = _required_query(query)
    terms = _query_terms(clean_query)
    matches = [
        record
        for record in records
        if _record_matches(
            record,
            query=clean_query,
            terms=terms,
            run_id=run_id,
            session_id=session_id,
        )
    ]
    ranked = sorted(
        matches,
        key=lambda record: (
            _record_score(record, query=clean_query, terms=terms),
            record.created_at,
            record.memory_id,
        ),
        reverse=True,
    )
    return _MemoryQueryMatches(all_matches=ranked, visible=ranked[:limit])


def render_memory_status_plain(payload: dict[str, Any]) -> str:
    store = payload.get("store") if isinstance(payload.get("store"), dict) else {}
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    records = payload.get("records") if isinstance(payload.get("records"), list) else []
    lines = [
        "Memory store",
        f"root: {store.get('root', '')}",
        f"path: {store.get('path', '')}",
        f"total: {summary.get('total', 0)}",
    ]
    by_scope = summary.get("by_scope")
    if isinstance(by_scope, dict):
        lines.append(
            "scope: "
            + " / ".join(f"{scope}={by_scope.get(scope, 0)}" for scope in VALID_SCOPES)
        )
    by_quality = summary.get("by_quality")
    if isinstance(by_quality, dict) and by_quality:
        lines.append(
            "quality: "
            + " / ".join(f"{key}={value}" for key, value in sorted(by_quality.items()))
        )
    if summary.get("hidden_records"):
        lines.append(f"hidden_records: {summary['hidden_records']}")
    if records:
        lines.append("records:")
        for record in records:
            lines.append(
                "- {record_id} / {scope} / {quality} / {summary}".format(
                    record_id=record.get("record_id", "unknown"),
                    scope=record.get("scope", "unknown"),
                    quality=record.get("quality", "unknown"),
                    summary=record.get("summary", ""),
                )
            )
    else:
        lines.append("records: none")
    return "\n".join(lines)


def render_memory_query_plain(payload: dict[str, Any]) -> str:
    store = payload.get("store") if isinstance(payload.get("store"), dict) else {}
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    results = payload.get("results") if isinstance(payload.get("results"), list) else []
    lines = [
        "Memory query",
        f"status: {payload.get('status', '')}",
        f"root: {store.get('root', '')}",
        f"query: {payload.get('query', '')}",
        "content_policy: summary_refs_provenance_only",
        f"scope: {payload.get('scope') or 'all'}",
        f"run_id: {payload.get('run_id') or 'all'}",
        f"session_id: {payload.get('session_id') or 'all'}",
        f"matched: {summary.get('matched', len(results))}",
        f"result_count: {len(results)}",
    ]
    if summary.get("hidden_records"):
        lines.append(f"hidden_records: {summary['hidden_records']}")
    controlled_expand = payload.get("controlled_expand")
    if isinstance(controlled_expand, dict):
        lines.append(f"controlled_expand: {controlled_expand.get('status', '')}")
        if "budget" in controlled_expand:
            lines.append(f"controlled_expand_budget: {controlled_expand['budget']}")
        if "used" in controlled_expand:
            lines.append(f"controlled_expand_used: {controlled_expand['used']}")
        content_policy = controlled_expand.get("content_policy")
        if isinstance(content_policy, str) and content_policy:
            lines.append(f"controlled_expand_content_policy: {content_policy}")
        materialized_results = controlled_expand.get("materialized_results")
        if isinstance(materialized_results, list):
            lines.append(f"controlled_expand_result_count: {len(materialized_results)}")
    if results:
        lines.append("results:")
        for record in results:
            lines.append(
                "- {record_id} / {scope} / {quality} / {summary}".format(
                    record_id=record.get("record_id", "unknown"),
                    scope=record.get("scope", "unknown"),
                    quality=record.get("quality", "unknown"),
                    summary=record.get("summary", ""),
                )
            )
            source_refs = record.get("source_refs")
            if source_refs:
                lines.append(f"  source_refs: {json.dumps(source_refs, sort_keys=True)}")
            provenance = record.get("provenance")
            if provenance:
                lines.append(f"  provenance: {json.dumps(provenance, sort_keys=True)}")
    else:
        lines.append("results: none")
    return "\n".join(lines)


def _memory_record_preview(record: MemoryRecord) -> dict[str, Any]:
    return {
        "record_id": record.memory_id,
        "scope": record.scope,
        "summary": record.summary,
        "source_refs": [dict(ref) for ref in record.source_refs],
        "provenance": dict(record.provenance),
        "created_at": record.created_at,
        "supersedes": list(record.supersedes),
        "quality": record.quality,
    }


def _memory_query_result(record: MemoryRecord) -> dict[str, Any]:
    return {
        "record_id": record.memory_id,
        "scope": record.scope,
        "summary": record.summary,
        "source_refs": [dict(ref) for ref in record.source_refs],
        "provenance": dict(record.provenance),
        "quality": record.quality,
    }


class _MemoryQueryMatches:
    def __init__(
        self,
        *,
        all_matches: list[MemoryRecord],
        visible: list[MemoryRecord],
    ) -> None:
        self.all_matches = all_matches
        self.visible = visible


def _required_query(query: str) -> str:
    if not isinstance(query, str) or not query.strip():
        raise ValueError("memory query must be a non-empty string")
    return query.strip()


def _query_terms(query: str) -> list[str]:
    return [term for term in query.casefold().split() if term]


def _record_matches(
    record: MemoryRecord,
    *,
    query: str,
    terms: list[str],
    run_id: str | None,
    session_id: str | None,
) -> bool:
    if run_id is not None and record.provenance.get("run_id") != run_id:
        return False
    if session_id is not None and record.provenance.get("session_id") != session_id:
        return False
    haystack = _record_search_text(record)
    return query.casefold() in haystack or any(term in haystack for term in terms)


def _record_score(record: MemoryRecord, *, query: str, terms: list[str]) -> int:
    haystack = _record_search_text(record)
    score = 0
    if query.casefold() in haystack:
        score += 10
    score += sum(1 for term in terms if term in haystack)
    return score


def _record_search_text(record: MemoryRecord) -> str:
    source_text = " ".join(str(value) for ref in record.source_refs for value in ref.values())
    provenance_text = " ".join(str(value) for value in record.provenance.values())
    return f"{record.summary} {source_text} {provenance_text}".casefold()


__all__ = [
    "VALID_SCOPES",
    "build_memory_query_payload",
    "build_memory_status_payload",
    "build_multi_worker_status_payload",
    "query_memory_records",
    "render_memory_query_plain",
    "render_memory_status_plain",
    "render_multi_worker_status_plain",
]
