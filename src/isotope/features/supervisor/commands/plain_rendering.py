"""Plain terminal rendering for supervise/advice command paths."""

from __future__ import annotations

from typing import Any


def print_supervise_plain(
    payload: dict[str, Any],
    report: Any,
    *,
    api: Any | None = None,
) -> None:
    if api is None:
        from isotope.features.supervisor import runner as api

    print("[Codex Supervisor supervise]")
    api._print_dashboard_plain(
        api._dashboard_payload(
            report,
            decision_requests=payload.get("decision_requests") or [],
        )
    )
    automation = payload["automation"]
    print()
    print("[托管自动化]")
    print(automation["reason"])
    if lifecycle_decision := payload.get("worker_lifecycle_decision"):
        print_worker_lifecycle_plain(lifecycle_decision)
    if auto_adopted := payload.get("auto_adopted"):
        for item in auto_adopted:
            print(
                f"自动接管：{item['name']} tmux={item['tmux_session']} cwd={item['cwd']}"
            )
    if goal_updates := payload.get("goal_updates"):
        print()
        print("[目标队列更新]")
        for item in goal_updates:
            archived = "，已归档" if item.get("archived") else ""
            print(f"{item['target_name']} / {item['status']}{archived}")
            if item.get("summary"):
                print(f"摘要：{item['summary']}")
    if cleanup_archived := payload.get("cleanup_archived"):
        print()
        print("[自动归档]")
        for item in cleanup_archived:
            target = item.get("name") or item.get("record_id")
            print(f"{item.get('kind', 'item')} {target}")
    if cleanup_deleted_worktrees := payload.get("cleanup_deleted_worktrees"):
        print()
        print("[自动 worktree 清理]")
        for item in cleanup_deleted_worktrees:
            target = item.get("target_name") or item.get("record_id")
            if item.get("deleted_worktree"):
                print(f"{target} / {item['deleted_worktree']}")
            else:
                print(f"{target} / {item.get('reason', 'skipped')}")
    if not automation["ready"]:
        print(f"启动：{automation['launch_hint']}")
        print(f"接管：{automation['adopt_hint']}")
    if llm_summary := payload.get("llm_summary"):
        print()
        print("[LLM 摘要]")
        print(llm_summary)
    if llm_action := payload.get("llm_action"):
        print()
        print(f"[{llm_action_section_title(llm_action)}]")
        print_llm_action_plain(llm_action, api=api)
    if llm_followup_action := payload.get("llm_followup_action"):
        print()
        print(f"[{llm_action_section_title(llm_followup_action, followup=True)}]")
        print_llm_action_plain(llm_followup_action, api=api)
    if auto_action := payload.get("auto_action"):
        print()
        print("[自动策略]")
        print(f"{auto_action['kind']} / {auto_action['reason']}")
    recommendation = payload["recommendation"]
    print()
    print("[建议]")
    print(f"{recommendation['label']} action={recommendation['action']}")
    if executed := payload.get("executed"):
        print_executed_plain(executed, api=api)
    if followup_executed := payload.get("followup_executed"):
        print_executed_plain(followup_executed, api=api)


def print_advice(args: Any, *, api: Any | None = None) -> None:
    if api is None:
        from isotope.features.supervisor import runner as api

    report = api._scan_report(args)
    action_report = api._action_report_for_workspace(args, report)
    active_goals = api._active_goal_dicts(args, include_status=True)
    explicit_goal = api._explicit_goal_text(args)
    payload = api._advice_payload(
        action_report,
        target_name=args.name,
        include_all_managed=args.llm_action or args.llm_execute,
        goal=api._goal_text(args),
        goal_workspace=api._goal_workspace(args),
        goal_target_name=api._goal_target_name(args),
        active_goals=None if explicit_goal else active_goals,
    )
    payload["workspace_scope"] = api._workspace_scope_payload(args, report, action_report)
    payload["active_goals"] = active_goals
    if args.llm_action or args.llm_execute:
        payload["recent_context_results"] = api._recent_context_results(
            args,
            action_report,
        )
        payload["recent_decision_answers"] = api._decision_answer_dicts(args)
        payload["worker_reviews"] = api._worker_review_context(args)
        payload["llm_action"] = api._decide_action_with_llm(
            args,
            action_report,
            payload,
        )
        api._promote_llm_command_suggestion(payload)
    if args.llm_execute:
        payload["executed"] = api._execute_llm_action(args, action_report, payload)
    elif args.execute:
        payload["executed"] = api._execute_advice(args, action_report, payload)
    if args.json:
        api._print_json(payload)
        return
    recommendation = payload["recommendation"]
    command_suggestion = payload["command_suggestion"]
    print("[Codex Supervisor 建议]")
    print(f"建议：{recommendation['label']}")
    print(f"动作：{recommendation['action']}")
    print(f"优先级：{recommendation['priority']}")
    if recommendation["target_session_id"]:
        print(f"目标：{recommendation['target_session_id']}")
    if llm_action := payload.get("llm_action"):
        print_advice_llm_action_plain(llm_action)
    if command_suggestion is None:
        print("命令：暂无可安全生成的命令草案。")
    else:
        print(f"命令：{command_suggestion['command']}")
    if executed := payload.get("executed"):
        print_executed_plain(executed, api=api)


def print_executed_plain(
    executed: dict[str, Any],
    *,
    api: Any | None = None,
) -> None:
    if api is None:
        from isotope.features.supervisor import runner as api

    if executed.get("kind") == "ask_user":
        print(f"等待拍板：{executed['question']}")
        return
    if executed.get("kind") == "fanout_launch_sessions":
        summary = executed.get("summary") or {}
        print(
            "fanout 已执行："
            f"{summary.get('launched', 0)} 个启动，"
            f"{summary.get('skipped', 0)} 个跳过"
        )
        for result in executed.get("results") or []:
            if isinstance(result, dict) and result.get("command"):
                print(f"已执行：{result['command']}")
        for result in executed.get("skipped") or []:
            if isinstance(result, dict) and result.get("reason"):
                print(f"已跳过：{result['reason']}")
        return
    if executed.get("skipped"):
        print(f"已跳过：{executed_activity_detail(executed, executed['reason'])}")
        return
    print(f"已执行：{executed_activity_detail(executed, executed['command'])}")


def print_worker_lifecycle_plain(decision: Any) -> None:
    if not isinstance(decision, dict):
        return
    print()
    print("[Worker 生命周期]")
    stage = _plain_text(decision.get("stage"), "unknown")
    next_step = _plain_text(decision.get("next_step"), "unknown")
    policy = decision.get("policy")
    policy_status = (
        _plain_text(policy.get("policy_status"), "unknown")
        if isinstance(policy, dict)
        else "unknown"
    )
    print(f"stage={stage} next_step={next_step} policy={policy_status}")
    if isinstance(policy, dict):
        remaining_step = policy.get("remaining_step")
        blocked_reason = policy.get("blocked_reason")
        if remaining_step:
            print(f"remaining_step={remaining_step}")
        if blocked_reason:
            print(f"blocked_reason={blocked_reason}")
    timeline_summary = _worker_lifecycle_timeline_summary(decision.get("timeline"))
    if timeline_summary:
        print(f"timeline: {timeline_summary}")


def _worker_lifecycle_timeline_summary(timeline: Any) -> str:
    if not isinstance(timeline, list):
        return ""
    parts: list[str] = []
    for item in timeline[:4]:
        if not isinstance(item, dict):
            continue
        stage = _plain_text(item.get("stage"), "unknown")
        action = _plain_text(item.get("action"), "unknown")
        status = _plain_text(item.get("status"), "unknown")
        parts.append(f"{stage}/{action} {status}")
    if len(timeline) > 4:
        parts.append(f"+{len(timeline) - 4} more")
    return "; ".join(parts)


def _plain_text(value: Any, fallback: str) -> str:
    return value if isinstance(value, str) and value else fallback


def llm_action_activity_kind(
    action: dict[str, Any],
    *,
    api: Any | None = None,
) -> str:
    if api is None:
        from isotope.features.supervisor import runner as api

    kind = str(action.get("kind") or "unknown")
    if api._is_merge_dispatch_launch_action(action):
        return "merge_dispatch"
    return kind


def llm_action_detail(action: dict[str, Any]) -> str:
    reason = action.get("reason")
    if isinstance(reason, str) and reason:
        return reason
    recommended = action.get("recommended_next_step")
    if isinstance(recommended, str) and recommended:
        return f"recommended_next_step={recommended}"
    return "no reason provided"


def is_program_routed_action(action: dict[str, Any]) -> bool:
    return isinstance(action.get("decision_source"), str) or isinstance(
        action.get("routing_reason"), str
    )


def llm_action_section_title(
    action: dict[str, Any],
    *,
    followup: bool = False,
) -> str:
    if is_program_routed_action(action):
        return "程序同轮后续动作" if followup else "程序路由动作"
    return "LLM 同轮后续动作" if followup else "LLM 白名单动作"


def print_llm_action_plain(
    action: dict[str, Any],
    *,
    api: Any | None = None,
) -> None:
    print(f"{llm_action_activity_kind(action, api=api)} / {llm_action_detail(action)}")
    print_llm_action_route_plain(action)
    print_ask_user_action_plain(action)


def print_llm_action_route_plain(action: dict[str, Any]) -> None:
    decision_source = action.get("decision_source")
    if isinstance(decision_source, str) and decision_source:
        print(f"动作来源：{decision_source}")
    routing_reason = action.get("routing_reason")
    if isinstance(routing_reason, str) and routing_reason:
        print(f"路由原因：{routing_reason}")


def print_advice_llm_action_plain(action: dict[str, Any]) -> None:
    if is_program_routed_action(action):
        print(f"程序路由动作：{action['kind']}")
        print(f"程序路由原因：{llm_action_detail(action)}")
    else:
        print(f"LLM 动作：{action['kind']}")
        print(f"LLM 原因：{llm_action_detail(action)}")
    print_llm_action_route_plain(action)
    print_ask_user_action_plain(action)


def executed_activity_detail(executed: dict[str, Any], detail: str) -> str:
    display_kind = executed.get("display_kind")
    if isinstance(display_kind, str) and display_kind:
        return f"{display_kind} / {detail}"
    return detail


def print_ask_user_action_plain(action: dict[str, Any]) -> None:
    if action.get("kind") != "ask_user":
        return
    question = action.get("question")
    if question:
        print(f"等待拍板：{question}")
    context_status = action.get("context_status")
    if context_status:
        print(f"上下文状态：{context_status}")
