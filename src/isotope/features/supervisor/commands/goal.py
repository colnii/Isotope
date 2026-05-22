"""Goal command handling for the Supervisor CLI."""

from __future__ import annotations

import argparse
import shlex
from pathlib import Path
from typing import Any

from isotope.features.supervisor.fanout import build_fanout_launch_plan
from isotope.features.supervisor.goal_planner import plan_supervisor_goals
from isotope.features.supervisor.goal_queue import (
    archive_supervisor_goal,
    build_supervisor_goal_queue_view,
    record_supervisor_goal,
)
from isotope.features.supervisor.registry import (
    default_registry_path,
    read_managed_records,
)


def handle_goal_command(args: argparse.Namespace, *, api: Any) -> int:
    payload = goal_payload(args, api=api)
    if args.json:
        api._print_json(payload)
    else:
        print_goal_plain(payload, api=api)
    return 0


def goal_payload(args: argparse.Namespace, *, api: Any | None = None) -> dict[str, Any]:
    if api is None:
        from isotope.features.supervisor import runner as api

    if args.goal_command == "add":
        goal = record_supervisor_goal(
            codex_home=Path(args.codex_home),
            cwd=Path(args.cwd),
            goal=goal_command_goal_text(args),
            target_name=args.target_name,
        )
        return {
            "status": "ok",
            "goal": goal.to_dict(),
            "active_goals": api._active_goal_dicts(args, include_status=True),
        }
    if args.goal_command == "plan":
        if args.fanout_execute and not args.write:
            raise ValueError("fanout-execute requires --write")
        provider = api.resolve_summary_provider_from_env(agent_name="supervisor")
        payload = plan_supervisor_goals(
            root=Path(args.cwd),
            codex_home=Path(args.codex_home),
            provider=provider,
            user_goal=goal_command_goal_text(args, required=False),
            write=args.write,
            limit=args.limit,
        )
        if args.fanout_execute:
            fanout_plan = build_fanout_launch_plan(
                payload,
                cwd=str(Path(args.cwd).expanduser()),
                limit=args.max_fanout_launches,
                running_target_names=api._running_managed_target_names_from_registry(
                    Path(args.codex_home)
                ),
                requires_human_review=False,
            )
            payload["fanout_plan"] = fanout_plan
            payload["executed"] = api._execute_fanout_launch_actions(args, fanout_plan)
        return payload
    if args.goal_command == "list":
        active_goals = api._active_goal_dicts(args, include_status=True)
        return {
            "status": "ok",
            "active_goals": active_goals,
            "queue_view": goal_queue_view(args, active_goals, api=api),
        }
    if args.goal_command == "archive":
        archived = archive_supervisor_goal(
            codex_home=Path(args.codex_home),
            goal_id=args.goal_id,
            status=args.status,
            summary=args.summary,
            next_step=args.next_step,
        )
        return {
            "status": "ok",
            "archived": archived,
            "active_goals": api._active_goal_dicts(args, include_status=True),
        }
    raise ValueError(f"unsupported goal command: {args.goal_command}")


def goal_command_goal_text(
    args: argparse.Namespace,
    *,
    required: bool = True,
) -> str | None:
    positional = optional_text(getattr(args, "goal_text", None))
    option = optional_text(getattr(args, "goal", None))
    if positional and option and positional != option:
        raise ValueError("goal positional argument and --goal must match when both are set")
    goal = option or positional
    if required and goal is None:
        raise ValueError("goal must not be empty")
    return goal


def optional_text(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def goal_queue_view(
    args: argparse.Namespace,
    active_goals: list[dict[str, Any]],
    *,
    api: Any | None = None,
) -> dict[str, list[dict[str, Any]]]:
    if api is None:
        from isotope.features.supervisor import runner as api

    return build_supervisor_goal_queue_view(
        active_goal_dicts_with_managed_protocol_status(
            active_goals,
            codex_home=Path(args.codex_home),
            api=api,
        ),
        running_target_names=api._running_managed_target_names_from_registry(
            Path(args.codex_home)
        ),
    )


def active_goal_dicts_with_managed_protocol_status(
    active_goals: list[dict[str, Any]],
    *,
    codex_home: Path,
    api: Any | None = None,
) -> list[dict[str, Any]]:
    if api is None:
        from isotope.features.supervisor import runner as api

    statuses = managed_protocol_statuses_by_name(codex_home, api=api)
    if not statuses:
        return active_goals
    enriched: list[dict[str, Any]] = []
    for goal in active_goals:
        target_name = goal.get("target_name")
        status = statuses.get(target_name) if isinstance(target_name, str) else None
        if status is None or goal.get("last_status") in {"blocked", "needs_user", "done"}:
            enriched.append(goal)
            continue
        merged = dict(goal)
        merged["last_status"] = status["status"]
        merged["worker_status"] = status["status"]
        if status.get("summary"):
            merged["last_summary"] = status["summary"]
        if status.get("next"):
            merged["last_next"] = status["next"]
        enriched.append(merged)
    return enriched


def managed_protocol_statuses_by_name(
    codex_home: Path,
    *,
    api: Any | None = None,
) -> dict[str, dict[str, str]]:
    if api is None:
        from isotope.features.supervisor import runner as api

    statuses: dict[str, dict[str, str]] = {}
    for record in read_managed_records(default_registry_path(codex_home)):
        excerpt = api._managed_process_log_excerpt(record.log_path) or ""
        protocol = api._supervisor_protocol_from_text(excerpt)
        status = protocol.get("status")
        if status not in {"done", "blocked", "needs_user"}:
            continue
        item = {"status": status}
        if summary := protocol.get("summary"):
            item["summary"] = summary
        if next_step := protocol.get("next"):
            item["next"] = next_step
        statuses[record.name] = item
    return statuses


def print_goal_plain(payload: dict[str, Any], *, api: Any | None = None) -> None:
    if api is None:
        from isotope.features.supervisor import runner as api

    goal = payload.get("goal")
    if isinstance(goal, dict):
        print(f"已添加目标：{goal['goal_id']}")
        print(f"目标：{goal['goal']}")
        print(f"工作区：{goal['cwd']}")
        print(f"worker：{goal['target_name']}")
    archived = payload.get("archived")
    if isinstance(archived, dict):
        print(f"已归档目标：{archived['goal_id']}")
    candidates = payload.get("candidates") or []
    if candidates:
        mode = "写入" if payload.get("mode") == "write" else "预览"
        print(f"LLM 目标规划：{mode}")
        plan_summary = payload.get("plan_summary")
        if isinstance(plan_summary, str) and plan_summary:
            print(f"计划摘要：{plan_summary}")
        phases = payload.get("phases") or []
        if phases:
            print("阶段/批次：")
            for phase in phases:
                if not isinstance(phase, dict):
                    continue
                name = phase.get("name") or "未命名阶段"
                print(f"- {name}")
                for goal in phase.get("goals") or []:
                    print(f"  目标：{goal}")
                for condition in phase.get("stop_conditions") or []:
                    print(f"  停止条件：{condition}")
                for condition in phase.get("acceptance_conditions") or []:
                    print(f"  验收条件：{condition}")
        recommendations = payload.get("parallel_recommendations") or []
        if recommendations:
            print("并行建议：")
            for item in recommendations:
                if not isinstance(item, dict):
                    continue
                batch = item.get("batch") or "未命名批次"
                targets = ", ".join(item.get("targets") or [])
                reason = item.get("reason") or ""
                print(f"- {batch}: {targets}")
                if reason:
                    print(f"  依据：{reason}")
        stop_conditions = payload.get("stop_conditions") or []
        if stop_conditions:
            print("停止条件：")
            for condition in stop_conditions:
                print(f"- {condition}")
        acceptance_conditions = payload.get("acceptance_conditions") or []
        if acceptance_conditions:
            print("验收条件：")
            for condition in acceptance_conditions:
                print(f"- {condition}")
        for item in candidates:
            print(f"- {item['target_name']} {item['goal']}")
            print(f"  依据：{item['reason']}")
    written_goals = payload.get("written_goals") or []
    if written_goals:
        print(f"已写入目标：{len(written_goals)}")
    if executed := payload.get("executed"):
        api._print_executed_plain(executed)
    print_goal_queue_view_plain(payload.get("queue_view"))
    goals = payload.get("active_goals") or []
    print(f"活跃目标：{len(goals)}")
    for item in goals:
        archive_command = shlex.join(
            [
                "isotope-supervisor",
                "goal",
                "archive",
                "--goal-id",
                item["goal_id"],
            ]
        )
        print(f"- {item['goal_id']} {item['goal']}")
        print(f"  cwd={item['cwd']} worker={item['target_name']}")
        if item.get("last_status"):
            print(f"  状态：{item['last_status']}")
        if item.get("last_summary"):
            print(f"  摘要：{item['last_summary']}")
        if item.get("last_next"):
            print(f"  下一步：{item['last_next']}")
        print(f"  归档：{archive_command}")


def print_goal_queue_view_plain(queue_view: object) -> None:
    if not isinstance(queue_view, dict):
        return
    print("队列视图：")
    for key, label in (
        ("pending", "pending"),
        ("running", "running"),
        ("blocked", "blocked"),
        ("needs_user", "needs_user"),
        ("done_recent", "done-recent"),
    ):
        raw_items = queue_view.get(key) or []
        items = [item for item in raw_items if isinstance(item, dict)]
        print(f"- {label}: {len(items)}")
        for item in items:
            target = item.get("target_name") or item.get("goal_id") or "unknown"
            goal_text = item.get("goal") or ""
            print(f"  - {target} {goal_text}".rstrip())
            if item.get("last_summary"):
                print(f"    摘要：{item['last_summary']}")
            if item.get("last_next"):
                print(f"    下一步：{item['last_next']}")
