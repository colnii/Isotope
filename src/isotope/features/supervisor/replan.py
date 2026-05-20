"""Read-only next-round advice for Supervisor worker reviews."""

from __future__ import annotations

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


def build_supervisor_replan(
    *,
    worker_reviews: dict[str, Any] | None,
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
            recommendations.append(_candidate_recommendation(kind, candidate, goal))

    for goal in goals:
        keys = _goal_keys(goal)
        if keys and keys.intersection(matched_goal_keys):
            continue
        recommendations.append(_active_goal_recommendation(goal))

    summary = _summary(recommendations, len(goals))
    return {
        "status": "ok",
        "summary": summary,
        "recommendations": recommendations,
        "safety": _safety(),
        "source": {
            "worker_review_status": worker_payload.get("status"),
            "worker_review_safety": worker_payload.get("safety") or {},
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
        "read_only": True,
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
        "read_only": True,
        "guardrail": _BUCKET_GUARDRAILS["continue_or_split"],
    }


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
) -> dict[str, int]:
    return {
        "total": len(recommendations),
        "review_then_merge": _count_kind(recommendations, "review_then_merge"),
        "continue_or_split": _count_kind(recommendations, "continue_or_split"),
        "archive_or_wait": _count_kind(recommendations, "archive_or_wait"),
        "recover_or_archive": _count_kind(recommendations, "recover_or_archive"),
        "active_goals": active_goal_count,
    }


def _count_kind(recommendations: list[dict[str, Any]], kind: str) -> int:
    return sum(1 for item in recommendations if item.get("kind") == kind)


def _safety() -> dict[str, Any]:
    return {
        "read_only": True,
        "auto_merge": False,
        "auto_archive": False,
        "delete_branch": False,
        "note": "只生成下一轮建议，不自动合并、不自动归档、不删除 worktree 或分支。",
    }
