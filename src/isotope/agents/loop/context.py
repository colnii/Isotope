"""Default context construction for Agent loop planner ticks."""

from __future__ import annotations

from typing import Any


def build_agent_loop_default_context(
    api: Any,
    run_id: str,
    *,
    control: dict[str, Any],
    memory_limit: int = 4,
) -> dict[str, Any]:
    """Build public runtime context for one provider planner decision."""
    return {
        "memory": _default_memory_context(
            api,
            run_id,
            control=control,
            limit=memory_limit,
        )
    }


def safe_agent_loop_default_context(
    default_context: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(default_context, dict):
        return {
            "memory": _empty_memory_context(
                query="",
                status="not_available",
                content_policy="memory_record_refs_expandable",
            )
        }
    memory = default_context.get("memory")
    if not isinstance(memory, dict):
        return {
            "memory": _empty_memory_context(
                query="",
                status="not_available",
                content_policy="memory_record_refs_expandable",
            )
        }
    return {"memory": _safe_memory_context(memory)}


def _default_memory_context(
    api: Any,
    run_id: str,
    *,
    control: dict[str, Any],
    limit: int,
) -> dict[str, Any]:
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise ValueError("memory_limit must be a positive integer")
    query = _default_memory_query(control, fallback_run_id=run_id)
    query_memory = getattr(api, "query_agent_loop_memory", None)
    if not callable(query_memory):
        return _empty_memory_context(
            query=query,
            status="not_available",
            content_policy="memory_record_refs_expandable",
        )

    scope_payloads = [
        _query_memory_scope(query_memory, run_id, query=query, scope="run", limit=limit),
    ]
    if _safe_string(control.get("session_id")):
        scope_payloads.append(
            _query_memory_scope(query_memory, run_id, query=query, scope="session", limit=limit)
        )
    results = _dedupe_memory_results(
        [
            result
            for payload in scope_payloads
            for result in _safe_memory_results(payload.get("results", []), limit=limit)
        ],
        limit=limit,
    )
    return {
        "source": "agent_loop_default_context",
        "query": query,
        "status": _combined_status(scope_payloads),
        "content_policy": "memory_record_refs_expandable",
        "result_count": len(results),
        "results": results,
        "scopes": [
            {
                "scope": scope,
                "status": _safe_string(payload.get("status", "unknown")),
                "result_count": len(
                    _safe_memory_results(payload.get("results", []), limit=limit)
                ),
            }
            for scope, payload in (
                (str(payload.get("scope", "")), payload) for payload in scope_payloads
            )
        ],
        "safety": {
            "runtime_invoked": True,
            "event_append": False,
            "content_policy": "memory_record_refs_expandable",
            "scopes": ["run", "session"],
        },
    }


def _query_memory_scope(
    query_memory: Any,
    run_id: str,
    *,
    query: str,
    scope: str,
    limit: int,
) -> dict[str, Any]:
    payload = query_memory(
        run_id,
        {
            "query": query,
            "limit": limit,
            "scope": scope,
        },
    )
    if not isinstance(payload, dict):
        return {
            "scope": scope,
            "status": "not_available",
            "content_policy": "memory_record_refs_expandable",
            "results": [],
        }
    result = dict(payload)
    result["scope"] = scope
    return result


def _empty_memory_context(
    *,
    query: str,
    status: str,
    content_policy: str,
) -> dict[str, Any]:
    return {
        "source": "agent_loop_default_context",
        "query": query,
        "status": status,
        "content_policy": content_policy,
        "result_count": 0,
        "results": [],
        "safety": {
            "runtime_invoked": True,
            "event_append": False,
            "content_policy": "memory_record_refs_expandable",
            "scopes": ["run", "session"],
        },
    }


def _default_memory_query(control: dict[str, Any], *, fallback_run_id: str) -> str:
    goal = control.get("goal")
    if isinstance(goal, str) and goal.strip():
        return goal.strip()
    run_id = control.get("run_id")
    if isinstance(run_id, str) and run_id.strip():
        return run_id.strip()
    return fallback_run_id


def _safe_memory_context(memory: dict[str, Any]) -> dict[str, Any]:
    results = _safe_memory_results(memory.get("results", []), limit=20)
    scopes = _safe_scope_summaries(memory.get("scopes", []), limit=10)
    return {
        "source": _safe_string(memory.get("source", "agent_loop_default_context")),
        "query": _safe_string(memory.get("query", "")),
        "status": _safe_string(memory.get("status", "unknown")),
        "content_policy": "memory_record_refs_expandable",
        "result_count": len(results),
        "results": results,
        "scopes": scopes,
        "safety": {
            "runtime_invoked": True,
            "event_append": False,
            "content_policy": "memory_record_refs_expandable",
            "scopes": ["run", "session"],
        },
    }


def _safe_memory_results(results: Any, *, limit: int) -> list[dict[str, Any]]:
    if not isinstance(results, list):
        return []
    safe_results: list[dict[str, Any]] = []
    for item in results[:limit]:
        if not isinstance(item, dict):
            continue
        safe_item: dict[str, Any] = {}
        for key in ("record_id", "scope", "summary", "quality"):
            value = item.get(key)
            if isinstance(value, str) and value:
                safe_item[key] = value
        source_refs = item.get("source_refs")
        if isinstance(source_refs, list):
            safe_item["source_refs"] = [
                {
                    str(ref_key): ref_value
                    for ref_key, ref_value in ref.items()
                    if isinstance(ref_key, str)
                    and isinstance(ref_value, (str, int, float, bool))
                }
                for ref in source_refs
                if isinstance(ref, dict)
            ]
        provenance = item.get("provenance")
        if isinstance(provenance, dict):
            safe_item["provenance"] = {
                str(key): value
                for key, value in provenance.items()
                if isinstance(key, str) and isinstance(value, (str, int, float, bool))
            }
        if safe_item:
            safe_results.append(safe_item)
    return safe_results


def _safe_scope_summaries(scopes: Any, *, limit: int) -> list[dict[str, Any]]:
    if not isinstance(scopes, list):
        return []
    safe_scopes = []
    for item in scopes[:limit]:
        if not isinstance(item, dict):
            continue
        scope = _safe_string(item.get("scope", ""))
        status = _safe_string(item.get("status", "unknown"))
        result_count = item.get("result_count", 0)
        if isinstance(result_count, bool) or not isinstance(result_count, int):
            result_count = 0
        if scope:
            safe_scopes.append(
                {
                    "scope": scope,
                    "status": status or "unknown",
                    "result_count": max(0, result_count),
                }
            )
    return safe_scopes


def _combined_status(payloads: list[dict[str, Any]]) -> str:
    statuses = [_safe_string(payload.get("status", "")) for payload in payloads]
    if any(status == "ok" for status in statuses):
        return "ok"
    if any(status for status in statuses):
        return statuses[0]
    return "unknown"


def _dedupe_memory_results(
    results: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen = set()
    for result in results:
        record_id = result.get("record_id")
        key = record_id if isinstance(record_id, str) and record_id else repr(result)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(result)
        if len(deduped) >= limit:
            break
    return deduped


def _safe_string(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""
