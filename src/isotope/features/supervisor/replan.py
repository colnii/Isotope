"""Read-only next-round advice for Supervisor worker reviews."""

from __future__ import annotations

import shlex
from typing import Any


_BUCKETS: tuple[tuple[str, str, str], ...] = (
    (
        "review_then_merge",
        "复查合并",
        "只提出复查合并建议；不自动合并、不删除 worktree 或分支。",
    ),
    (
        "continue_or_split",
        "继续拆分",
        "只提出继续/拆分建议；不自动启动、不自动归档、不自动合并。",
    ),
    (
        "archive_or_wait",
        "归档等待",
        "只提出归档/等待建议；不自动归档、不删除登记或 worktree。",
    ),
    (
        "recover_or_archive",
        "恢复/归档",
        "只提出恢复/归档建议；不自动恢复、不自动归档、不删除 worktree 或分支。",
    ),
)
_BUCKET_LABELS = {kind: label for kind, label, _guardrail in _BUCKETS}
_BUCKET_GUARDRAILS = {kind: guardrail for kind, _label, guardrail in _BUCKETS}

_INTEGRATION_GROUPS: tuple[str, ...] = (
    "ready_to_integrate",
    "already_integrated",
    "needs_review",
    "conflict_risk",
)
_INTEGRATION_KIND = {
    "ready_to_integrate": "review_then_merge",
    "already_integrated": "archive_or_wait",
    "needs_review": "continue_or_split",
    "conflict_risk": "recover_or_archive",
}
_INTEGRATION_NEXT_ACTIONS = {
    "ready_to_integrate": [
        "交给动态 Codex worker 做最终 diff/test 复查",
        "复查通过后由主控或人工执行 merge",
        "merge 后再次运行 integration-review 确认 main 已包含 worker HEAD",
    ],
    "already_integrated": [
        "复查 main 是否包含 worker HEAD",
        "确认无需后续动作后归档 worker 记录",
    ],
    "needs_review": [
        "按 integration-review 原因复查 worker worktree",
        "要求 worker 提交、继续或拆分下一轮任务",
    ],
    "conflict_risk": [
        "不要自动合并",
        "交给人工或专门 worker 处理 rebase/merge conflict",
        "冲突处理后重新运行 integration-review",
    ],
}


def build_supervisor_replan(
    *,
    worker_reviews: dict[str, Any] | None,
    integration_reviews: dict[str, Any] | None = None,
    active_goals: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Build read-only advice for the next Supervisor loop.

    The function consumes existing read models only. It does not start workers,
    merge branches, archive records, or touch git state.
    """

    worker_payload = worker_reviews if isinstance(worker_reviews, dict) else {}
    goals = [goal for goal in active_goals or [] if isinstance(goal, dict)]
    goal_index = _active_goal_index(goals)
    matched_goal_keys: set[str] = set()
    recommendations: list[dict[str, Any]] = []
    recommendation_index: dict[str, dict[str, Any]] = {}

    automation_candidates = worker_payload.get("automation_candidates")
    if not isinstance(automation_candidates, dict):
        automation_candidates = {}

    for kind, _label, _guardrail in _BUCKETS:
        raw_items = automation_candidates.get(kind)
        if not isinstance(raw_items, list):
            continue
        for candidate in raw_items:
            if not isinstance(candidate, dict):
                continue
            goal, goal_keys = _match_active_goal(candidate, goal_index)
            matched_goal_keys.update(goal_keys)
            recommendation = _candidate_recommendation(kind, candidate, goal)
            recommendations.append(recommendation)
            _index_recommendation(recommendation_index, recommendation)

    integration_payload = integration_reviews if isinstance(integration_reviews, dict) else {}
    _append_integration_recommendations(
        recommendations=recommendations,
        recommendation_index=recommendation_index,
        integration_reviews=integration_payload,
        goal_index=goal_index,
        matched_goal_keys=matched_goal_keys,
    )

    for goal in goals:
        keys = _goal_keys(goal)
        if keys and keys.intersection(matched_goal_keys):
            continue
        recommendations.append(_active_goal_recommendation(goal))

    merge_candidates = _merge_candidates(recommendations)
    summary = _summary(
        recommendations,
        len(goals),
        integration_reviews=integration_payload,
        merge_candidate_count=len(merge_candidates),
    )
    return {
        "status": "ok",
        "summary": summary,
        "recommendations": recommendations,
        "merge_candidates": merge_candidates,
        "safety": _safety(),
        "source": {
            "worker_review_status": worker_payload.get("status"),
            "worker_review_safety": worker_payload.get("safety") or {},
            "integration_review_status": integration_payload.get("status"),
            "integration_review_safety": integration_payload.get("safety") or {},
            "integration_review_base": integration_payload.get("base_ref"),
        },
    }


def render_supervisor_replan_plain(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload, dict) else {}
    summary = summary if isinstance(summary, dict) else {}
    safety = payload.get("safety") if isinstance(payload, dict) else {}
    safety = safety if isinstance(safety, dict) else {}
    lines = [
        "[Supervisor Replan]",
        (
            "总建议：{total} / 复查合并 {review_then_merge} / 继续拆分 "
            "{continue_or_split} / 归档等待 {archive_or_wait} / 恢复/归档 "
            "{recover_or_archive} / active goals {active_goals}"
        ).format(
            total=summary.get("total", 0),
            review_then_merge=summary.get("review_then_merge", 0),
            continue_or_split=summary.get("continue_or_split", 0),
            archive_or_wait=summary.get("archive_or_wait", 0),
            recover_or_archive=summary.get("recover_or_archive", 0),
            active_goals=summary.get("active_goals", 0),
        ),
        f"安全：{safety.get('note') or '只读建议。'}",
    ]
    if _has_integration_summary(summary):
        lines.append(
            "integration：ready_to_integrate {ready_to_integrate} / "
            "already_integrated {already_integrated} / needs_review {needs_review} / "
            "conflict_risk {conflict_risk}".format(
                ready_to_integrate=summary.get("ready_to_integrate", 0),
                already_integrated=summary.get("already_integrated", 0),
                needs_review=summary.get("needs_review", 0),
                conflict_risk=summary.get("conflict_risk", 0),
            )
        )
    merge_candidates = payload.get("merge_candidates")
    if isinstance(merge_candidates, list) and merge_candidates:
        lines.extend(["", "可交给动态 Codex worker 的合并候选："])
        for candidate in merge_candidates:
            if not isinstance(candidate, dict):
                continue
            lines.append(
                "- {name} / {record_id} / {branch} @ {commit}".format(
                    name=candidate.get("name") or "未知目标",
                    record_id=candidate.get("record_id") or "无 worker record",
                    branch=candidate.get("branch") or "未知分支",
                    commit=candidate.get("worker_commit") or "未知提交",
                )
            )
    for item in payload.get("recommendations", []):
        if not isinstance(item, dict):
            continue
        lines.extend(
            [
                "",
                "{label}：{name} / {record_id}".format(
                    label=item.get("label") or "建议",
                    name=item.get("name") or item.get("target_name") or "未知目标",
                    record_id=item.get("record_id") or "无 worker record",
                ),
                f"  原因：{item.get('reason') or '无'}",
                f"  护栏：{item.get('guardrail') or '只读建议。'}",
            ]
        )
        next_actions = item.get("next_actions")
        if isinstance(next_actions, list) and next_actions:
            lines.append("  下一步：")
            lines.extend(f"    - {action}" for action in next_actions if action)
    return "\n".join(lines)


def _candidate_recommendation(
    kind: str,
    candidate: dict[str, Any],
    goal: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "label": _BUCKET_LABELS[kind],
        "record_id": candidate.get("record_id"),
        "name": candidate.get("name"),
        "target_name": _target_name(candidate),
        "goal": goal,
        "cwd": candidate.get("cwd"),
        "branch": candidate.get("branch"),
        "risk_level": candidate.get("risk_level"),
        "reason": candidate.get("reason"),
        "next_actions": _string_list(candidate.get("next_actions")),
        "validation_commands": _string_list(candidate.get("validation_commands")),
        "reviewer_command": candidate.get("reviewer_command"),
        "read_snapshot": True,
        "guardrail": _BUCKET_GUARDRAILS[kind],
    }


def _active_goal_recommendation(goal: dict[str, Any]) -> dict[str, Any]:
    target_name = goal.get("target_name")
    name = target_name if isinstance(target_name, str) and target_name else None
    return {
        "kind": "continue_or_split",
        "label": _BUCKET_LABELS["continue_or_split"],
        "record_id": None,
        "name": name,
        "target_name": name,
        "goal": goal,
        "cwd": None,
        "branch": None,
        "risk_level": "medium",
        "reason": (
            "active goal 仍在队列中，但 worker-review 没有对应候选；"
            "建议继续观察、恢复 worker 或拆出下一轮任务。"
        ),
        "next_actions": [
            "检查 active goal 最近状态",
            "确认是否已有对应 worker 在运行",
            "必要时继续推进或拆出下一轮 worker",
        ],
        "validation_commands": [],
        "reviewer_command": None,
        "read_snapshot": True,
        "guardrail": _BUCKET_GUARDRAILS["continue_or_split"],
    }


def _append_integration_recommendations(
    *,
    recommendations: list[dict[str, Any]],
    recommendation_index: dict[str, dict[str, Any]],
    integration_reviews: dict[str, Any],
    goal_index: dict[str, dict[str, Any]],
    matched_goal_keys: set[str],
) -> None:
    groups = integration_reviews.get("groups")
    if not isinstance(groups, dict):
        return
    for integration_group in _INTEGRATION_GROUPS:
        raw_items = groups.get(integration_group)
        if not isinstance(raw_items, list):
            continue
        for worker in raw_items:
            if not isinstance(worker, dict):
                continue
            goal, goal_keys = _match_active_goal(worker, goal_index)
            matched_goal_keys.update(goal_keys)
            recommendation = _integration_recommendation(integration_group, worker, goal)
            existing = _find_indexed_recommendation(recommendation_index, recommendation)
            if existing is None:
                recommendations.append(recommendation)
                _index_recommendation(recommendation_index, recommendation)
            else:
                existing.update(recommendation)
                _index_recommendation(recommendation_index, existing)


def _integration_recommendation(
    integration_group: str,
    worker: dict[str, Any],
    goal: dict[str, Any] | None,
) -> dict[str, Any]:
    kind = _INTEGRATION_KIND[integration_group]
    target_name = _target_name(worker)
    return {
        "kind": kind,
        "label": _BUCKET_LABELS[kind],
        "record_id": worker.get("record_id"),
        "name": worker.get("name"),
        "target_name": target_name,
        "goal": goal,
        "cwd": worker.get("cwd"),
        "branch": worker.get("branch"),
        "risk_level": _integration_risk_level(integration_group),
        "reason": worker.get("reason"),
        "next_actions": list(_INTEGRATION_NEXT_ACTIONS[integration_group]),
        "validation_commands": _integration_validation_commands(worker),
        "reviewer_command": None,
        "read_snapshot": True,
        "guardrail": _BUCKET_GUARDRAILS[kind],
        "integration_group": integration_group,
        "base_ref": worker.get("base_ref"),
        "base_commit": worker.get("base_commit"),
        "worker_commit": worker.get("worker_commit"),
        "main_contains_worker": worker.get("main_contains_worker"),
        "worker_contains_main": worker.get("worker_contains_main"),
        "merge_conflict": worker.get("merge_conflict"),
        "dynamic_codex_candidate": integration_group == "ready_to_integrate",
    }


def _integration_risk_level(integration_group: str) -> str:
    if integration_group == "ready_to_integrate":
        return "medium"
    if integration_group == "already_integrated":
        return "low"
    return "high"


def _integration_validation_commands(worker: dict[str, Any]) -> list[str]:
    cwd = worker.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        return []
    quoted_cwd = shlex.quote(cwd)
    return [
        f"git -C {quoted_cwd} status --short --branch",
        f"git -C {quoted_cwd} log --oneline -1",
    ]


def _active_goal_index(goals: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for goal in goals:
        for key in _goal_keys(goal):
            index.setdefault(key, goal)
    return index


def _match_active_goal(
    candidate: dict[str, Any],
    goal_index: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any] | None, set[str]]:
    for key in _candidate_keys(candidate):
        goal = goal_index.get(key)
        if goal is not None:
            return goal, _goal_keys(goal)
    return None, set()


def _index_recommendation(
    recommendation_index: dict[str, dict[str, Any]],
    recommendation: dict[str, Any],
) -> None:
    for key in _candidate_keys(recommendation):
        recommendation_index.setdefault(key, recommendation)


def _find_indexed_recommendation(
    recommendation_index: dict[str, dict[str, Any]],
    recommendation: dict[str, Any],
) -> dict[str, Any] | None:
    for key in _candidate_keys(recommendation):
        existing = recommendation_index.get(key)
        if existing is not None:
            return existing
    return None


def _candidate_keys(candidate: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for value in (candidate.get("name"), candidate.get("target_name")):
        if isinstance(value, str) and value:
            keys.add(f"target:{value}")
    record_id = candidate.get("record_id")
    if isinstance(record_id, str) and record_id:
        keys.add(f"record:{record_id}")
        keys.add(f"session:managed:{record_id}")
    return keys


def _goal_keys(goal: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    target_name = goal.get("target_name")
    if isinstance(target_name, str) and target_name:
        keys.add(f"target:{target_name}")
    session_id = goal.get("worker_session_id")
    if isinstance(session_id, str) and session_id:
        keys.add(f"session:{session_id}")
        if session_id.startswith("managed:"):
            keys.add(f"record:{session_id.removeprefix('managed:')}")
    goal_id = goal.get("goal_id")
    if isinstance(goal_id, str) and goal_id:
        keys.add(f"goal:{goal_id}")
    return keys


def _target_name(candidate: dict[str, Any]) -> str | None:
    value = candidate.get("target_name") or candidate.get("name")
    return value if isinstance(value, str) and value else None


def _string_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, str) and item]


def _summary(
    recommendations: list[dict[str, Any]],
    active_goal_count: int,
    *,
    integration_reviews: dict[str, Any],
    merge_candidate_count: int,
) -> dict[str, int]:
    summary = {
        "total": len(recommendations),
        "review_then_merge": _count_kind(recommendations, "review_then_merge"),
        "continue_or_split": _count_kind(recommendations, "continue_or_split"),
        "archive_or_wait": _count_kind(recommendations, "archive_or_wait"),
        "recover_or_archive": _count_kind(recommendations, "recover_or_archive"),
        "active_goals": active_goal_count,
    }
    if _has_integration_payload(integration_reviews):
        summary.update(_integration_summary(integration_reviews))
        summary["merge_candidates"] = merge_candidate_count
    return summary


def _count_kind(recommendations: list[dict[str, Any]], kind: str) -> int:
    return sum(1 for item in recommendations if item.get("kind") == kind)


def _integration_summary(integration_reviews: dict[str, Any]) -> dict[str, int]:
    raw_summary = integration_reviews.get("summary")
    raw_summary = raw_summary if isinstance(raw_summary, dict) else {}
    return {
        group: raw_summary.get(group, 0) if isinstance(raw_summary.get(group, 0), int) else 0
        for group in _INTEGRATION_GROUPS
    }


def _has_integration_payload(integration_reviews: dict[str, Any]) -> bool:
    return isinstance(integration_reviews.get("summary"), dict) or isinstance(
        integration_reviews.get("groups"), dict
    )


def _has_integration_summary(summary: dict[str, Any]) -> bool:
    return any(summary.get(group, 0) for group in _INTEGRATION_GROUPS)


def _merge_candidates(recommendations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for recommendation in recommendations:
        if recommendation.get("integration_group") != "ready_to_integrate":
            continue
        candidates.append(
            {
                "record_id": recommendation.get("record_id"),
                "name": recommendation.get("name"),
                "target_name": recommendation.get("target_name"),
                "cwd": recommendation.get("cwd"),
                "branch": recommendation.get("branch"),
                "worker_commit": recommendation.get("worker_commit"),
                "base_ref": recommendation.get("base_ref"),
                "reason": recommendation.get("reason"),
                "handoff": "dynamic_codex_worker",
                "read_snapshot": True,
            }
        )
    return candidates


def _safety() -> dict[str, Any]:
    return {
        "read_snapshot": True,
        "auto_merge": False,
        "auto_archive": False,
        "delete_branch": False,
        "note": "只生成下一轮建议，不自动合并、不自动归档、不删除 worktree 或分支。",
    }
