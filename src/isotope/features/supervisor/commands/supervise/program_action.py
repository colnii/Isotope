"""Program-prepared Supervisor action context for supervise/loop."""

from __future__ import annotations

from typing import Any

from isotope.features.supervisor.lifecycle import worker_lifecycle_execution_action


def select_required_supervisor_action(
    args: Any,
    action_report: Any,
    *,
    active_goals: list[dict[str, Any]],
    explicit_goal: str | None,
    fanout_status: dict[str, Any] | None,
    fanout_paused: bool,
    worker_role_guard: dict[str, Any] | None,
    fanout_plan: dict[str, Any] | None,
    api: Any,
) -> dict[str, Any] | None:
    if fanout_paused:
        return _candidate(
            reason="fanout_paused",
            action=api._fanout_paused_action(fanout_status),
        )
    if fanout_plan is not None:
        return _candidate(
            reason="fanout_plan",
            action=api._fanout_llm_action(fanout_plan),
        )
    if worker_role_guard is not None:
        return _candidate(
            reason="worker_role_guard",
            action=api._recursive_worker_role_guard_action(worker_role_guard),
        )
    if api._loop_without_autonomous_scope(
        args,
        action_report,
        active_goals,
        explicit_goal,
    ):
        return _candidate(
            reason="idle_loop",
            action=api._idle_loop_llm_action(),
        )
    return None


def build_supervisor_prepared_action_context(
    args: Any,
    action_report: Any,
    *,
    payload: dict[str, Any] | None = None,
    active_goals: list[dict[str, Any]],
    explicit_goal: str | None,
    fanout_status: dict[str, Any] | None,
    fanout_paused: bool,
    worker_role_guard: dict[str, Any] | None,
    merge_dispatch: dict[str, Any] | None,
    fanout_plan: dict[str, Any] | None,
    lifecycle_execution: dict[str, Any] | None,
    api: Any,
) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    facts = _prepared_facts(payload or {}, active_goals=active_goals)
    if lifecycle_execution is not None:
        candidates.append(
            _candidate(
                reason="worker_lifecycle_execution",
                action=worker_lifecycle_execution_action(lifecycle_execution),
            )
        )
    if merge_dispatch is not None:
        if merge_dispatch.get("status") == "worker_already_running":
            action = api._merge_dispatch_already_running_action(merge_dispatch)
        else:
            action = merge_dispatch["launch_spec"]
        candidates.append(
            _candidate(
                reason="merge_dispatch",
                action=action,
            )
        )
    if not candidates and not facts:
        return None
    context = {
        "kind": "supervisor_prepared_action_context",
        "source": "program",
    }
    if candidates:
        context["candidates"] = candidates
    if facts:
        context["facts"] = facts
    return context


def _candidate(*, reason: str, action: dict[str, Any]) -> dict[str, Any]:
    return {
        "reason": reason,
        "action": action,
    }


def _prepared_facts(
    payload: dict[str, Any],
    *,
    active_goals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    active_goal_fact = _active_goals_fact(active_goals)
    if active_goal_fact is not None:
        facts.append(active_goal_fact)
    current_batch_fact = _current_batch_fact(payload.get("current_batch"))
    if current_batch_fact is not None:
        facts.append(current_batch_fact)
    decision_request_fact = _decision_requests_fact(payload.get("decision_requests"))
    if decision_request_fact is not None:
        facts.append(decision_request_fact)
    context_results_fact = _recent_context_results_fact(
        payload.get("recent_context_results")
    )
    if context_results_fact is not None:
        facts.append(context_results_fact)
    worker_reviews_fact = _worker_reviews_fact(payload.get("worker_reviews"))
    if worker_reviews_fact is not None:
        facts.append(worker_reviews_fact)
    delete_candidates_fact = _target_list_fact(
        "delete_worktree_candidates",
        payload.get("delete_worktree_candidates"),
    )
    if delete_candidates_fact is not None:
        facts.append(delete_candidates_fact)
    capacity_decisions_fact = _capacity_decisions_fact(
        payload.get("capacity_decisions")
    )
    if capacity_decisions_fact is not None:
        facts.append(capacity_decisions_fact)
    return facts


def _active_goals_fact(active_goals: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not active_goals:
        return None
    statuses: dict[str, int] = {}
    for goal in active_goals:
        status = _short_string(goal.get("last_status"))
        if status is not None:
            statuses[status] = statuses.get(status, 0) + 1
    fact: dict[str, Any] = {
        "kind": "active_goals",
        "count": len(active_goals),
        "target_names": _target_names(active_goals),
    }
    if statuses:
        fact["statuses"] = statuses
    return fact


def _current_batch_fact(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    target_names = _string_list(value.get("target_names"))
    summary = _small_mapping(value.get("summary"))
    if not target_names and not summary:
        return None
    fact: dict[str, Any] = {
        "kind": "current_batch",
        "target_names": target_names,
    }
    if summary:
        fact["summary"] = summary
    return fact


def _decision_requests_fact(value: Any) -> dict[str, Any] | None:
    items = _dict_items(value)
    if not items:
        return None
    context_statuses: dict[str, int] = {}
    for item in items:
        status = _short_string(item.get("context_status"))
        if status is not None:
            context_statuses[status] = context_statuses.get(status, 0) + 1
    fact: dict[str, Any] = {
        "kind": "decision_requests",
        "count": len(items),
        "target_names": _target_names(items),
    }
    if context_statuses:
        fact["context_statuses"] = context_statuses
    return fact


def _recent_context_results_fact(value: Any) -> dict[str, Any] | None:
    items = _dict_items(value)
    if not items:
        return None
    return {
        "kind": "recent_context_results",
        "count": len(items),
        "queries": [
            query
            for query in (_short_string(item.get("query")) for item in items[:5])
            if query is not None
        ],
    }


def _worker_reviews_fact(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    workers = _dict_items(value.get("workers"))
    merge_suitable = 0
    for worker in workers:
        next_decision = worker.get("next_decision")
        if isinstance(next_decision, dict) and next_decision.get("merge_suitable") is True:
            merge_suitable += 1
    fact: dict[str, Any] = {
        "kind": "worker_reviews",
        "status": _short_string(value.get("status")),
        "decision_summary": _small_mapping(value.get("decision_summary")),
        "merge_suitable": merge_suitable,
    }
    return {key: item for key, item in fact.items() if item not in (None, {}, [])}


def _target_list_fact(kind: str, value: Any) -> dict[str, Any] | None:
    items = _dict_items(value)
    if not items:
        return None
    return {
        "kind": kind,
        "count": len(items),
        "target_names": _target_names(items),
    }


def _capacity_decisions_fact(value: Any) -> dict[str, Any] | None:
    items = _dict_items(value)
    if not items:
        return None
    ready: list[str] = []
    request_input: list[str] = []
    blocked: list[str] = []
    for item in items:
        capacity_id = _short_string(item.get("capacity_id"))
        if capacity_id is None:
            continue
        next_action = _short_string(item.get("next_action"))
        if next_action == "call_capacity" and item.get("can_execute_agent_loop") is True:
            ready.append(capacity_id)
        elif next_action == "request_input":
            request_input.append(capacity_id)
        elif next_action == "blocked":
            blocked.append(capacity_id)
    return {
        "kind": "capacity_decisions",
        "ready": ready[:5],
        "request_input": request_input[:5],
        "blocked": blocked[:5],
    }


def _dict_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _target_names(items: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for item in items:
        target_name = _short_string(item.get("target_name") or item.get("name"))
        if target_name is not None and target_name not in names:
            names.append(target_name)
    return names[:5]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = _short_string(item)
        if text is not None:
            result.append(text)
    return result[:5]


def _small_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, Any] = {}
    for key, item in value.items():
        text_key = _short_string(key)
        if text_key is None:
            continue
        scalar = _small_scalar(item)
        if scalar is not None:
            result[text_key] = scalar
        if len(result) >= 8:
            break
    return result


def _small_scalar(value: Any) -> str | int | float | bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value
    return _short_string(value)


def _short_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    if not text:
        return None
    if len(text) <= 160:
        return text
    return text[:159] + "\u2026"
