"""LLM planner provider selection and failure handling for Supervisor."""

from __future__ import annotations

from typing import Any


def decide_action_with_llm(
    args: Any,
    report: Any,
    payload: dict[str, Any],
    *,
    api: Any | None = None,
) -> dict[str, Any]:
    if api is None:
        from isotope.features.supervisor import runner as api

    if not api._has_llm_action_target(
        report,
        payload.get("command_suggestions"),
        payload.get("delete_worktree_candidates"),
    ):
        return _generate_llm_action_decision(
            api,
            report,
            payload,
            ContextRequiredSummaryProvider(),
        )
    try:
        provider = api.resolve_summary_provider_from_env(agent_name="supervisor")
        return _generate_llm_action_decision(api, report, payload, provider)
    except ValueError as exc:
        error = str(exc)
        failure_event = api._record_failure_event(
            args,
            event_type="llm_planner_invalid_response",
            report=report,
            payload=payload,
            error_summary=error,
        )
        if api._failure_retry_exhausted(args, failure_event):
            return api._failure_decision_request_action(
                event=failure_event,
                question=api._failure_question("llm_planner_invalid_response"),
                reason="LLM planner failure retry limit exceeded",
            )
        reason = f"LLM 动作无效，已跳过执行：{error}"
        return {
            "kind": "monitor",
            "target_name": None,
            "reason": reason,
            "command_suggestion": None,
            "error": error,
        }


def _generate_llm_action_decision(
    api: Any,
    report: Any,
    payload: dict[str, Any],
    provider: Any,
) -> dict[str, Any]:
    return api.generate_llm_action_decision(
        report,
        payload["command_suggestions"],
        provider,
        payload.get("recent_context_results"),
        payload.get("active_goals"),
        payload.get("recent_decision_answers"),
        payload.get("worker_reviews"),
        payload.get("delete_worktree_candidates"),
        capacity_decisions=payload.get("capacity_decisions"),
        worker_lifecycle_decision=payload.get("worker_lifecycle_decision"),
    )


class ContextRequiredSummaryProvider:
    def summarize(self, messages: list[dict[str, str]]) -> str:
        raise AssertionError("LLM provider should not be called without Supervisor context")
