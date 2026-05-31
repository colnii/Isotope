"""Default context construction for Agent loop planner ticks."""

from __future__ import annotations

from typing import Any


def build_agent_loop_default_context(
    api: Any,
    run_id: str,
    *,
    control: dict[str, Any],
    memory_limit: int = 3,
) -> dict[str, Any]:
    """Build low-sensitive runtime context for one provider planner decision."""
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
                content_policy="summary_refs_provenance_only",
            )
        }
    memory = default_context.get("memory")
    if not isinstance(memory, dict):
        return {
            "memory": _empty_memory_context(
                query="",
                status="not_available",
                content_policy="summary_refs_provenance_only",
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
            content_policy="summary_refs_provenance_only",
        )

    payload = query_memory(
        run_id,
        {
            "query": query,
            "limit": limit,
        },
    )
    results = _safe_memory_results(payload.get("results", []), limit=limit)
    return {
        "source": "agent_loop_default_context",
        "query": query,
        "status": _safe_string(payload.get("status", "unknown")),
        "content_policy": _safe_string(
            payload.get("content_policy", "summary_refs_provenance_only")
        ),
        "result_count": len(results),
        "results": results,
        "safety": {
            "runtime_invoked": True,
            "event_append": False,
            "content_policy": "summary_refs_provenance_only",
        },
    }


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
            "content_policy": "summary_refs_provenance_only",
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
    return {
        "source": _safe_string(memory.get("source", "agent_loop_default_context")),
        "query": _safe_string(memory.get("query", "")),
        "status": _safe_string(memory.get("status", "unknown")),
        "content_policy": _safe_string(
            memory.get("content_policy", "summary_refs_provenance_only")
        ),
        "result_count": len(results),
        "results": results,
        "safety": {
            "runtime_invoked": True,
            "event_append": False,
            "content_policy": "summary_refs_provenance_only",
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


def _safe_string(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""
