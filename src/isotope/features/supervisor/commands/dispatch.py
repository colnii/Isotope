"""Command dispatch for the Supervisor CLI."""

from __future__ import annotations

import argparse
from typing import Any

from .cleanup import handle_cleanup_command as _handle_cleanup_command
from .dashboard import handle_dashboard_command as _handle_dashboard_command
from .handlers.agent_group import (
    handle_agent_group_command as _handle_agent_group_command,
)
from .handlers.capacity import handle_capacity_command as _handle_capacity_command
from .handlers.context import handle_context_command as _handle_context_command
from .handlers.decision import handle_decision_command as _handle_decision_command
from .handlers.goal import handle_goal_command as _handle_goal_command
from .handlers.memory import (
    handle_memory_command as _handle_memory_command,
    handle_worker_event_command as _handle_worker_event_command,
    handle_worker_manager_command as _handle_worker_manager_command,
)
from .handlers.replan import handle_replan_command as _handle_replan_command
from .handlers.state import handle_state_command as _handle_state_command
from .handlers.worktree_audit import (
    handle_worktree_audit_command as _handle_worktree_audit_command,
)
from .merge import (
    handle_integration_review_command as _handle_integration_review_command,
    handle_merge_work_order_command as _handle_merge_work_order_command,
)


def _runner_api(api: Any | None) -> Any:
    if api is not None:
        return api
    from isotope.features.supervisor import runner

    return runner


def handle_research_command(args: argparse.Namespace, *, api) -> int:
    if args.research_action == "providers":
        payload = api.list_research_providers()
        if args.json:
            api._print_json(payload)
        else:
            api._print_research_providers_plain(payload)
        return 0
    if args.research_action == "list":
        payload = api.list_research_artifacts(
            api.Path(args.root),
            artifact_type=args.artifact_type,
            limit=args.limit,
        )
        if args.json:
            api._print_json(payload)
        else:
            api._print_research_list_plain(payload)
        return 0
    if args.research_action == "inspect":
        if not args.run_id or not args.artifact_id:
            raise ValueError("supervisor research inspect requires --run-id and --artifact-id")
        payload = api.inspect_research_artifact(
            api.Path(args.root),
            run_id=args.run_id,
            artifact_id=args.artifact_id,
        )
        if args.json:
            api._print_json(payload)
        else:
            api._print_research_inspect_plain(payload)
        return 0
    if args.research_action == "promote":
        if not args.run_id or not args.artifact_id:
            raise ValueError("supervisor research promote requires --run-id and --artifact-id")
        if not args.agent_id or not args.thread_id:
            raise ValueError("supervisor research promote requires --agent-id and --thread-id")
        payload = api.build_research_memory_promotion_payload(
            api.Path(args.root),
            run_id=args.run_id,
            artifact_id=args.artifact_id,
            agent_id=args.agent_id,
            thread_id=args.thread_id,
            scope=args.scope,
            quality=args.quality,
            proposal_id=args.proposal_id,
        )
        if args.json:
            api._print_json(payload)
        else:
            api._print_research_promotion_plain(payload)
        return 0
    if not args.query:
        raise ValueError("supervisor research search requires --query")
    flow = api.ResearchFlow.in_process(
        api.Path(args.root),
        provider=api.build_research_provider(
            args.provider,
            workspace_root=args.workspace_root or api.Path.cwd(),
            codex_executable=args.codex_executable,
            codex_home=args.codex_home,
            model=args.model,
            timeout_seconds=args.timeout_seconds,
            max_attempts=args.max_attempts,
            tavily_api_key=args.tavily_api_key,
            tavily_config_path=args.tavily_config,
            tavily_enable_network=args.tavily_enable_network,
            tavily_timeout_seconds=args.tavily_timeout_seconds,
            tavily_max_results=args.tavily_max_results,
        ),
    )
    payload = flow.search(args.query).to_dict()
    if args.json:
        api._print_json(payload)
    else:
        research = payload.get("research") or {}
        print("[Codex Supervisor Research]")
        print(f"status: {payload['status']}")
        print(f"query: {research.get('query') or payload.get('query', '')}")
        print(f"evidence: {research.get('evidence_status', '')}")
        error = payload.get("error")
        if isinstance(error, dict):
            print(f"retryable: {str(error.get('retryable', False)).lower()}")
            print(f"error: {error.get('message', '')}")
        api._print_research_artifacts_plain(payload)
    return 0


def handle_screen_command(args: argparse.Namespace, *, api) -> int:
    if args.screen_action == "report":
        payload = api.report_screen_artifacts(
            api.Path(args.root),
            run_id=args.run_id,
        )
        if args.json:
            api._print_json(payload)
        else:
            api._print_screen_report_plain(payload)
        return 0
    if args.screen_action == "inspect":
        if not args.artifact_id:
            raise ValueError("supervisor screen inspect requires --artifact-id")
        payload = api.inspect_screen_artifact(
            api.Path(args.root),
            run_id=args.run_id,
            artifact_id=args.artifact_id,
        )
        if args.json:
            api._print_json(payload)
        else:
            api._print_screen_inspect_plain(payload)
        return 0
    raise ValueError("supervisor screen action is not supported")


COMMAND_HANDLERS = {
    "agent-group": _handle_agent_group_command,
    "dashboard": _handle_dashboard_command,
    "integration-review": _handle_integration_review_command,
    "merge-work-order": _handle_merge_work_order_command,
    "goal": _handle_goal_command,
    "cleanup": _handle_cleanup_command,
    "capacity": _handle_capacity_command,
    "context": _handle_context_command,
    "decision": _handle_decision_command,
    "memory": _handle_memory_command,
    "research": handle_research_command,
    "replan": _handle_replan_command,
    "screen": handle_screen_command,
    "state": _handle_state_command,
    "worker-event": _handle_worker_event_command,
    "worker-manager": _handle_worker_manager_command,
    "worktree-audit": _handle_worktree_audit_command,
}


def run_cli_impl(
    argv: list[str] | None = None,
    *,
    api: Any | None = None,
) -> int:
    api = _runner_api(api)
    parser = api._build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "scan":
            api._print_report(args)
            return 0
        if args.command in COMMAND_HANDLERS:
            return COMMAND_HANDLERS[args.command](args, api=api)
        if args.command == "advise":
            api._validate_execution_modes(args)
            api._print_advice(args)
            return 0
        if args.command == "supervise":
            api._validate_execution_modes(args)
            api._run_supervise(args)
            return 0
        if args.command == "loop":
            api._normalize_loop_execution_mode(args)
            api._validate_execution_modes(args)
            api._run_supervise(args)
            return 0
        if args.command == "up":
            payload = api._up_payload(args)
            if args.json:
                api._print_json(payload)
            else:
                api._print_daemon_plain(payload)
            return 0
        if args.command in {"check", "overnight-check"}:
            payload = api._overnight_check_payload(args)
            if args.json:
                api._print_json(payload)
            else:
                api._print_overnight_check_plain(payload)
            return 0
        if args.command == "daemon":
            if (
                args.daemon_command == "watcher"
                and args.watcher_command == "run"
            ):
                api._run_daemon_watcher(args)
                return 0
            payload = api._daemon_payload(args)
            if args.json:
                api._print_json(payload)
            elif args.daemon_command == "watcher":
                api._print_watcher_plain(payload)
            else:
                api._print_daemon_plain(payload)
            return 0
        if args.command == "watch":
            if args.interval <= 0:
                raise ValueError("interval must be positive")
            if args.iterations is not None and args.iterations <= 0:
                raise ValueError("iterations must be positive")
            iterations = args.iterations
            count = 0
            previous_fingerprint: tuple[object, ...] | None = None
            previous_bell_fingerprint: tuple[object, ...] | None = None
            while iterations is None or count < iterations:
                printed, previous_fingerprint, previous_bell_fingerprint = api._print_report(
                    args,
                    previous_fingerprint=previous_fingerprint,
                    previous_bell_fingerprint=previous_bell_fingerprint,
                )
                if printed and iterations is not None and count + 1 < iterations:
                    print()
                count += 1
                if iterations is None or count < iterations:
                    api._sleep(args.interval)
            return 0
        if args.command == "web":
            api._run_web(args)
            return 0
        if args.command == "launch":
            record = api.launch_managed_codex(
                codex_home=api.Path(args.codex_home),
                cwd=api.Path(args.cwd),
                name=args.name,
                prompt=args.prompt,
                codex_bin=args.codex_bin,
                codex_model=args.codex_model,
                codex_config=tuple(args.codex_config),
                backend=args.backend,
                tmux_session=args.tmux_session,
                worker_role=getattr(args, "worker_role", "worker"),
                popen=api.subprocess.Popen,
                run=api.subprocess.run,
            )
            if args.json:
                api._print_json({"status": "ok", "managed": record.to_dict()})
            else:
                print(f"已启动托管 Codex：{record.name}")
                print(f"pid：{record.pid}")
                print(f"日志：{record.log_path}")
            return 0
        if args.command == "worker-review":
            payload = api.collect_worker_reviews(codex_home=api.Path(args.codex_home))
            if args.json:
                api._print_json(payload)
            else:
                print(api.render_worker_review_plain(payload))
            return 0
        if args.command == "trace":
            payload = api._lifecycle_trace_payload(args)
            if args.json:
                api._print_json(payload)
            else:
                api._print_lifecycle_trace_plain(payload)
            return 0
        if args.command == "resume":
            record = api.resume_managed_codex(
                codex_home=api.Path(args.codex_home),
                cwd=api.Path(args.cwd),
                name=args.name,
                prompt=args.prompt,
                session_id=args.session_id,
                last=args.last,
                codex_bin=args.codex_bin,
                codex_model=args.codex_model,
                codex_config=tuple(args.codex_config),
                popen=api.subprocess.Popen,
            )
            if args.json:
                api._print_json({"status": "ok", "managed": record.to_dict()})
            else:
                print(f"已恢复托管 Codex：{record.name}")
                target = "--last" if record.resume_last else record.resume_session_id
                print(f"session：{target}")
                print(f"pid：{record.pid}")
                print(f"日志：{record.log_path}")
            return 0
        if args.command == "adopt":
            if args.session_id:
                record = api.adopt_codex_session(
                    codex_home=api.Path(args.codex_home),
                    cwd=api.Path(args.cwd) if args.cwd else None,
                    name=args.name,
                    session_id=args.session_id,
                    prompt=args.prompt,
                )
            else:
                if not args.cwd:
                    raise ValueError("--cwd is required for --tmux-session adoption")
                record = api.adopt_tmux_session(
                    codex_home=api.Path(args.codex_home),
                    cwd=api.Path(args.cwd),
                    name=args.name,
                    tmux_session=args.tmux_session,
                    prompt=args.prompt,
                    run=api.subprocess.run,
                )
            if args.json:
                api._print_json({"status": "ok", "managed": record.to_dict()})
            else:
                print(f"已接管 Codex 会话：{record.name}")
                if record.tmux_session:
                    print(f"tmux：{record.tmux_session}")
                if record.resume_session_id:
                    print(f"session：{record.resume_session_id}")
            return 0
        if args.command == "discover":
            payload = api._discover_payload(args)
            if args.json:
                api._print_json(payload)
            else:
                api._print_discover_plain(payload)
            return 0
        if args.command == "archive":
            record = api.archive_managed_codex(
                codex_home=api.Path(args.codex_home),
                name=args.name,
            )
            if args.json:
                api._print_json({"status": "ok", "managed": record.to_dict()})
            else:
                print(f"已归档托管 Codex：{record.name}")
                if record.tmux_session:
                    print(f"tmux：{record.tmux_session}")
            return 0
        if args.command == "send":
            result = api.send_to_managed_codex(
                codex_home=api.Path(args.codex_home),
                name=args.name,
                text=args.text,
                run=api.subprocess.run,
            )
            if args.json:
                api._print_json(
                    {
                        "status": "ok",
                        "text": result.text,
                        "managed": {
                            "name": result.record.name,
                            "record_id": result.record.record_id,
                            "tmux_session": result.record.tmux_session,
                        },
                    }
                )
            else:
                print(f"已发送到托管 Codex：{result.record.name}")
                print(f"tmux：{result.record.tmux_session}")
                print(f"内容：{result.text}")
            return 0
        if args.command == "repair-hooks":
            repairs = api.repair_tmux_bell_hooks(
                codex_home=api.Path(args.codex_home),
                run=api.subprocess.run,
            )
            if args.json:
                api._print_json(
                    {
                        "status": "ok",
                        "repairs": [repair.to_dict() for repair in repairs],
                    }
                )
            else:
                if not repairs:
                    print("没有需要修复的托管 tmux 会话。")
                for repair in repairs:
                    print(
                        f"{repair.tmux_session} / {repair.name}: {repair.status}"
                        + (f" / {repair.message}" if repair.message else "")
                    )
            return 0
        if args.command == "start-here":
            payload = api._start_here_payload(args)
            if args.json:
                api._print_json(payload)
            else:
                api._print_start_here_plain(payload)
            return 0
        if args.command == "guide":
            payload = api._guide_payload(args)
            if args.json:
                api._print_json(payload)
            else:
                api._print_guide_plain(payload)
            return 0
    except KeyboardInterrupt:
        return 130
    except ValueError as exc:
        if getattr(args, "json", False):
            api._print_json(
                {
                    "status": "error",
                    "error": {
                        "code": "codex_supervisor_runner_error",
                        "message": str(exc),
                    },
                }
            )
        else:
            print(f"error: {exc}")
        return 2
    parser.error(f"unknown command: {args.command}")
    return 2

__all__ = ("COMMAND_HANDLERS", "handle_research_command", "run_cli_impl")
