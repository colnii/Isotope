"""Daemon command payloads and plain renderers for the Supervisor CLI."""

from __future__ import annotations

import argparse
import shlex
from pathlib import Path
from typing import Any

from isotope.features.supervisor.daemon import (
    build_supervisor_daemon_night_summary,
    run_supervisor_watcher,
    start_supervisor_daemon,
    start_supervisor_watcher,
    stop_supervisor_daemon,
    stop_supervisor_watcher,
    supervisor_daemon_status,
    supervisor_watcher_status,
    watchdog_supervisor_daemon,
)
from isotope.features.supervisor.registry import (
    default_registry_path,
    read_managed_records,
)


def _default_api() -> Any:
    from isotope.features.supervisor import runner as api

    return api


def daemon_payload(
    args: argparse.Namespace,
    *,
    api: Any | None = None,
) -> dict[str, Any]:
    if api is None:
        api = _default_api()
    if args.daemon_command == "watcher":
        return watcher_payload(args, api=api)
    if args.daemon_command == "start":
        daemon = start_daemon_from_args(args, api=api)
    elif args.daemon_command == "status":
        daemon = supervisor_daemon_status(codex_home=Path(args.codex_home))
        daemon["activity"] = daemon_activity_payload(
            Path(args.codex_home),
            daemon,
            api=api,
        )
    elif args.daemon_command == "stop":
        daemon = stop_supervisor_daemon(codex_home=Path(args.codex_home))
    elif args.daemon_command == "watchdog":
        daemon = watchdog_supervisor_daemon(codex_home=Path(args.codex_home))
    else:
        raise ValueError(f"unknown daemon command: {args.daemon_command}")
    return {
        "status": "ok",
        "daemon": daemon,
    }


def up_payload(args: argparse.Namespace, *, api: Any | None = None) -> dict[str, Any]:
    if api is None:
        api = _default_api()
    daemon = start_daemon_from_args(args, api=api)
    daemon["activity"] = daemon_activity_payload(
        Path(args.codex_home),
        daemon,
        api=api,
    )
    return {
        "status": "ok",
        "daemon": daemon,
    }


def start_daemon_from_args(
    args: argparse.Namespace,
    *,
    api: Any | None = None,
) -> dict[str, Any]:
    if api is None:
        api = _default_api()
    if args.interval <= 0:
        raise ValueError("interval must be positive")
    if args.limit <= 0:
        raise ValueError("limit must be positive")
    if args.max_continue_count < 0:
        raise ValueError("max_continue_count must be zero or positive")
    if args.max_context_requests < 0:
        raise ValueError("max_context_requests must be zero or positive")
    if args.decision_timeout < 0:
        raise ValueError("decision_timeout must be zero or positive")
    if args.max_failure_retries < 0:
        raise ValueError("max_failure_retries must be zero or positive")
    if args.max_run_minutes < 0:
        raise ValueError("max_run_minutes must be zero or positive")
    if args.max_fanout_launches <= 0:
        raise ValueError("max_fanout_launches must be positive")
    if getattr(args, "goal_low_water", 0) < 0:
        raise ValueError("goal_low_water must be zero or positive")
    if getattr(args, "goal_replenish_limit", 1) <= 0:
        raise ValueError("goal_replenish_limit must be positive")
    worker_profile = api._worker_profile_from_args(args)
    queued_goal = queue_daemon_goal_from_args(args, api=api)
    daemon = start_supervisor_daemon(
        codex_home=Path(args.codex_home),
        interval=args.interval,
        limit=args.limit,
        stale_after=args.stale_after,
        active_within=args.active_within,
        prompt_cooldown=args.prompt_cooldown,
        max_continue_count=args.max_continue_count,
        max_context_requests=args.max_context_requests,
        decision_timeout=args.decision_timeout,
        max_failure_retries=args.max_failure_retries,
        max_run_minutes=args.max_run_minutes,
        max_fanout_launches=args.max_fanout_launches,
        goal_low_water=args.goal_low_water,
        goal_replenish_limit=args.goal_replenish_limit,
        goal_replenish_prompt=args.goal_replenish_prompt,
        name=args.name,
        goal=None,
        llm_summary=args.llm_summary,
        auto_adopt=args.auto_adopt,
        merge_dispatch_execute=getattr(args, "merge_dispatch_execute", False),
        auto_merge_promote=getattr(args, "auto_merge_promote", False),
        worker_codex_model=api._worker_codex_model(args, profile=worker_profile),
        worker_codex_config=api._worker_codex_config(args, profile=worker_profile),
        webhook_url=args.webhook_url,
        webhook_secret=args.webhook_secret,
    )
    if queued_goal is not None:
        daemon["queued_goal"] = queued_goal
    return daemon


def queue_daemon_goal_from_args(
    args: argparse.Namespace,
    *,
    api: Any | None = None,
) -> dict[str, Any] | None:
    if api is None:
        api = _default_api()
    goal = api._explicit_goal_text(args)
    if goal is None:
        return None
    queued = api.record_supervisor_goal(
        codex_home=Path(args.codex_home),
        cwd=api._explicit_goal_workspace(args),
        goal=goal,
    )
    return queued.to_dict()


def daemon_activity_payload(
    codex_home: Path,
    daemon: dict[str, Any],
    *,
    api: Any | None = None,
) -> dict[str, Any]:
    if api is None:
        api = _default_api()
    if daemon.get("status") != "running":
        active_goals = api._active_goal_dicts_for_codex_home(
            codex_home,
            include_status=True,
        )
        activity: dict[str, Any] = {
            "recent_llm_action": None,
            "recent_ci": None,
            "recent_execution": None,
            "recent_worker": None,
            "night_summary": build_supervisor_daemon_night_summary(
                active_goals=active_goals,
                managed_workers=[],
                integration_reviews=None,
                recent_ci=None,
                recent_execution=None,
                recent_worker=None,
                merge_worker_name=api.MERGE_DISPATCH_TARGET_NAME,
            ),
        }
        if active_goals:
            activity["active_goals"] = active_goals
        return activity
    log_path = daemon.get("log_path")
    daemon_log = read_tail_text(log_path if isinstance(log_path, str) else None)
    api._sync_managed_worker_failures(
        codex_home=codex_home,
        max_run_minutes=max_run_minutes_from_daemon_command(daemon),
    )
    recent_ci = recent_ci_from_log(daemon_log)
    recent_execution = recent_execution_from_log(daemon_log)
    recent_worker = recent_worker_payload(codex_home, api=api)
    active_goals = api._active_goal_dicts_for_codex_home(
        codex_home,
        include_status=True,
    )
    managed_workers = daemon_managed_worker_payloads(codex_home, api=api)
    integration_reviews = daemon_integration_reviews(codex_home, api=api)
    activity = {
        "recent_llm_action": recent_llm_action_from_log(daemon_log),
        "recent_ci": recent_ci,
        "recent_execution": recent_execution,
        "recent_worker": recent_worker,
        "night_summary": build_supervisor_daemon_night_summary(
            active_goals=active_goals,
            managed_workers=managed_workers,
            integration_reviews=integration_reviews,
            recent_ci=recent_ci,
            recent_execution=recent_execution,
            recent_worker=recent_worker,
            merge_worker_name=api.MERGE_DISPATCH_TARGET_NAME,
        ),
    }
    if active_goals:
        activity["active_goals"] = active_goals
    return activity


def max_run_minutes_from_daemon_command(daemon: dict[str, Any]) -> int:
    command = daemon.get("command")
    if not isinstance(command, list):
        return 0
    for index, item in enumerate(command):
        if item != "--max-run-minutes" or index + 1 >= len(command):
            continue
        try:
            return max(0, int(command[index + 1]))
        except (TypeError, ValueError):
            return 0
    return 0


def read_tail_text(path_text: str | None, *, max_bytes: int = 64 * 1024) -> str:
    if not path_text:
        return ""
    path = Path(path_text).expanduser()
    try:
        size = path.stat().st_size
    except OSError:
        return ""
    try:
        with path.open("rb") as handle:
            if size > max_bytes:
                handle.seek(size - max_bytes)
            data = handle.read()
    except OSError:
        return ""
    return data.decode("utf-8", errors="ignore")


def recent_llm_action_from_log(text: str) -> dict[str, str] | None:
    lines = text.splitlines()
    recent: dict[str, str] | None = None
    for index, raw_line in enumerate(lines):
        if raw_line.strip() != "[LLM 白名单动作]":
            continue
        for action_line in lines[index + 1 :]:
            line = action_line.strip()
            if not line:
                continue
            if " / " in line:
                kind, reason = line.split(" / ", 1)
            else:
                kind, reason = line, ""
            recent = {"kind": kind.strip(), "reason": reason.strip()}
            break
    return recent


def recent_execution_from_log(text: str) -> dict[str, str] | None:
    recent: dict[str, str] | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("已执行："):
            recent = {
                "status": "executed",
                "detail": line.removeprefix("已执行：").strip(),
            }
        elif line.startswith("已跳过："):
            recent = {
                "status": "skipped",
                "detail": line.removeprefix("已跳过：").strip(),
            }
    return recent


def recent_ci_from_log(text: str) -> dict[str, str] | None:
    recent: dict[str, str] | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("CI："):
            recent = status_detail_from_text(line.removeprefix("CI：").strip())
        elif line.startswith("CI:"):
            recent = status_detail_from_text(line.removeprefix("CI:").strip())
    return recent


def status_detail_from_text(text: str) -> dict[str, str]:
    if " / " in text:
        status, detail = text.split(" / ", 1)
    else:
        status, detail = text, ""
    return {"status": status.strip(), "detail": detail.strip()}


def daemon_integration_reviews(
    codex_home: Path,
    *,
    api: Any | None = None,
) -> dict[str, Any]:
    if api is None:
        api = _default_api()
    try:
        return api.collect_integration_reviews(
            codex_home=codex_home,
            base_ref="main",
            include_unfinished=False,
            run_test_gate=False,
            run_candidate_validation=False,
        )
    except Exception as exc:  # pragma: no cover - defensive status surface
        return {
            "status": "error",
            "error": str(exc),
            "summary": {"ready_to_integrate": 0},
        }


def daemon_managed_worker_payloads(
    codex_home: Path,
    *,
    api: Any | None = None,
) -> list[dict[str, Any]]:
    if api is None:
        api = _default_api()
    return [
        daemon_managed_worker_payload(codex_home=codex_home, record=record, api=api)
        for record in read_managed_records(default_registry_path(codex_home))
    ]


def daemon_managed_worker_payload(
    *,
    codex_home: Path,
    record: Any,
    api: Any | None = None,
) -> dict[str, Any]:
    if api is None:
        api = _default_api()
    model, config = codex_worker_options_from_command(record.command)
    protocol = api._supervisor_protocol_from_text(
        api._managed_process_log_excerpt(record.log_path) or ""
    )
    status = protocol.get("status") or record.status
    process_running = (
        api._pid_is_running(record.pid)
        if record.backend != "tmux" and record.pid
        else None
    )
    failure = api._lane_failure_payload(codex_home=codex_home, record=record)
    if failure is not None:
        status = "error"
    if (
        record.backend != "tmux"
        and status in {"launched", "resumed", "working"}
        and not process_running
    ):
        status = "exited"
    return {
        "name": record.name,
        "record_id": record.record_id,
        "backend": record.backend,
        "pid": record.pid,
        "process_running": process_running,
        "model": model,
        "config": config,
        "status": status,
        "summary": protocol.get("summary"),
        "next": protocol.get("next"),
        "log_path": record.log_path,
        **({"failure": failure} if failure is not None else {}),
    }


def recent_worker_payload(
    codex_home: Path,
    *,
    api: Any | None = None,
) -> dict[str, Any] | None:
    workers = daemon_managed_worker_payloads(codex_home, api=api)
    if not workers:
        return None
    return workers[-1]


def codex_worker_options_from_command(
    command: tuple[str, ...],
) -> tuple[str | None, list[str]]:
    model: str | None = None
    config: list[str] = []
    index = 0
    while index < len(command):
        item = command[index]
        if item in {"-m", "--model"} and index + 1 < len(command):
            model = command[index + 1]
            index += 2
            continue
        if item in {"-c", "--config"} and index + 1 < len(command):
            config.append(command[index + 1])
            index += 2
            continue
        index += 1
    return model, config


def watcher_payload(
    args: argparse.Namespace,
    *,
    api: Any | None = None,
) -> dict[str, Any]:
    if args.watcher_command == "start":
        if args.interval <= 0:
            raise ValueError("interval must be positive")
        watcher = start_supervisor_watcher(
            codex_home=Path(args.codex_home),
            interval=args.interval,
        )
    elif args.watcher_command == "status":
        watcher = supervisor_watcher_status(codex_home=Path(args.codex_home))
    elif args.watcher_command == "stop":
        watcher = stop_supervisor_watcher(codex_home=Path(args.codex_home))
    else:
        raise ValueError(f"unknown watcher command: {args.watcher_command}")
    return {
        "status": "ok",
        "watcher": watcher,
    }


def overnight_check_payload(
    args: argparse.Namespace,
    *,
    api: Any | None = None,
) -> dict[str, Any]:
    if api is None:
        api = _default_api()
    codex_home = Path(args.codex_home)
    daemon = supervisor_daemon_status(codex_home=codex_home)
    daemon["activity"] = daemon_activity_payload(codex_home, daemon, api=api)
    watcher = supervisor_watcher_status(codex_home=codex_home)
    goals = {
        "status": "ok",
        "active_goals": api._active_goal_dicts_for_codex_home(
            codex_home,
            include_status=True,
        ),
    }
    integration_review = api.collect_integration_reviews(
        codex_home=codex_home,
        base_ref=args.base,
        include_unfinished=True,
    )
    cleanup = {
        "status": "ok",
        "candidates": api._cleanup_candidate_dicts(codex_home),
    }
    integration_summary = integration_review.get("summary") or {}
    return {
        "status": "ok",
        "summary": {
            "daemon_status": daemon.get("status"),
            "watcher_status": watcher.get("status"),
            "active_goals": len(goals["active_goals"]),
            "integration_review": {
                "total": integration_summary.get("total", 0),
                "ready_to_integrate": integration_summary.get("ready_to_integrate", 0),
                "already_integrated": integration_summary.get("already_integrated", 0),
                "needs_review": integration_summary.get("needs_review", 0),
                "conflict_risk": integration_summary.get("conflict_risk", 0),
            },
            "cleanup_candidates": len(cleanup["candidates"]),
        },
        "daemon": daemon,
        "watcher": watcher,
        "goals": goals,
        "integration_review": integration_review,
        "cleanup": cleanup,
    }


def run_daemon_watcher(args: argparse.Namespace, *, api: Any | None = None) -> None:
    if api is None:
        api = _default_api()
    if args.interval <= 0:
        raise ValueError("interval must be positive")
    if args.iterations is not None and args.iterations <= 0:
        raise ValueError("iterations must be positive")
    for payload in run_supervisor_watcher(
        codex_home=Path(args.codex_home),
        interval=args.interval,
        iterations=args.iterations,
    ):
        if args.json:
            api._print_json(payload)
        else:
            print_watcher_run_plain(payload)


def print_daemon_plain(payload: dict[str, Any]) -> None:
    daemon = payload["daemon"]
    status = daemon["status"]
    print("[Codex Supervisor daemon]")
    if status == "running":
        action = daemon.get("action")
        if action in {"already_running", "alive"}:
            label = "后台 loop 仍在运行"
        elif action == "restarted":
            label = "后台 loop 已由 watchdog 重启"
        else:
            label = "已启动后台 loop"
        print(label)
        print(f"pid：{daemon['pid']}")
        if "previous_pid" in daemon:
            print(f"旧 pid：{daemon['previous_pid']}")
        print(f"日志：{daemon['log_path']}")
        print("命令：" + shlex.join(daemon["command"]))
        print_daemon_activity_plain(daemon.get("activity"))
        return
    if status == "stopped":
        print("已停止后台 loop")
        print(f"pid：{daemon['pid']}")
        print(f"状态文件：{daemon['state_path']}")
        print_daemon_activity_plain(daemon.get("activity"))
        return
    if status == "stale":
        print("后台 loop 状态已过期，进程可能已经退出。")
        print(f"pid：{daemon['pid']}")
        print(f"日志：{daemon['log_path']}")
        print_daemon_activity_plain(daemon.get("activity"))
        return
    print("后台 loop 未运行。")
    print(f"状态文件：{daemon['state_path']}")
    print_daemon_activity_plain(daemon.get("activity"))


def print_daemon_activity_plain(activity: Any) -> None:
    if not isinstance(activity, dict):
        return
    action = activity.get("recent_llm_action")
    ci = activity.get("recent_ci")
    execution = activity.get("recent_execution")
    worker = activity.get("recent_worker")
    active_goals = activity.get("active_goals")
    night_summary = activity.get("night_summary")
    if (
        not action
        and not ci
        and not execution
        and not worker
        and not active_goals
        and not night_summary
    ):
        return
    print("最近活动：")
    if isinstance(night_summary, dict):
        merge_label = "运行中" if night_summary.get("merge_worker_running") else "未运行"
        print(
            "夜间摘要：active goals {active_goals} / running workers {running_workers} / "
            "ready_to_integrate {ready_to_integrate} / merge worker {merge_label}".format(
                active_goals=night_summary.get("active_goals", 0),
                running_workers=night_summary.get("running_workers", 0),
                ready_to_integrate=night_summary.get("ready_to_integrate", 0),
                merge_label=merge_label,
            )
        )
    if isinstance(action, dict):
        print(f"LLM 动作：{action.get('kind') or '未知'} / {action.get('reason') or '无'}")
    if isinstance(ci, dict):
        print(f"CI：{ci.get('status') or 'unknown'} / {ci.get('detail') or '无'}")
    if isinstance(execution, dict):
        print(
            f"执行结果：{execution.get('status') or 'unknown'} / "
            f"{execution.get('detail') or '无'}"
        )
    if isinstance(worker, dict):
        config = worker.get("config")
        config_text = ", ".join(config) if isinstance(config, list) and config else "无"
        print(
            f"最近 worker：{worker.get('name') or '未知'} "
            f"模型={worker.get('model') or '未指定'} 配置={config_text} "
            f"状态={worker.get('status') or '未知'}"
        )
        if worker.get("summary"):
            print(f"worker 摘要：{worker['summary']}")
    if isinstance(active_goals, list) and active_goals:
        print("活跃目标：")
        for item in active_goals:
            status = item.get("last_status") or "未汇报"
            print(
                f"- {item.get('target_name') or item.get('goal_id')}: "
                f"{status} / {item.get('goal') or '无目标文本'}"
            )
            if item.get("last_summary"):
                print(f"  摘要：{item['last_summary']}")


def print_watcher_plain(payload: dict[str, Any]) -> None:
    watcher = payload["watcher"]
    status = watcher["status"]
    print("[Codex Supervisor watcher]")
    if status == "running":
        action = watcher.get("action")
        label = "周期 watcher 仍在运行" if action == "already_running" else "已启动周期 watcher"
        print(label)
        print(f"pid：{watcher['pid']}")
        print(f"日志：{watcher['log_path']}")
        print("命令：" + shlex.join(watcher["command"]))
        return
    if status == "stopped":
        print("已停止周期 watcher")
        print(f"pid：{watcher['pid']}")
        print(f"状态文件：{watcher['state_path']}")
        return
    if status == "stale":
        print("周期 watcher 状态已过期，进程可能已经退出。")
        print(f"pid：{watcher['pid']}")
        print(f"日志：{watcher['log_path']}")
        return
    print("周期 watcher 未运行。")
    print(f"状态文件：{watcher['state_path']}")


def print_watcher_run_plain(payload: dict[str, Any]) -> None:
    watchdog = payload["watchdog"]
    print(f"[Codex Supervisor watcher] 第 {payload['iteration']} 轮")
    print(f"动作：{watchdog.get('action')}")
    print(f"状态：{watchdog.get('status')}")
    if watchdog.get("pid") is not None:
        print(f"pid：{watchdog['pid']}")


def print_overnight_check_plain(payload: dict[str, Any]) -> None:
    summary = payload["summary"]
    integration = summary["integration_review"]
    print("[Codex Supervisor overnight check]")
    print(f"daemon：{summary['daemon_status']}")
    print(f"watcher：{summary['watcher_status']}")
    print(f"活跃目标：{summary['active_goals']}")
    print(
        "integration-review："
        f"total={integration['total']} "
        f"ready={integration['ready_to_integrate']} "
        f"integrated={integration['already_integrated']} "
        f"review={integration['needs_review']} "
        f"conflict={integration['conflict_risk']}"
    )
    print(f"可归档项：{summary['cleanup_candidates']}")
