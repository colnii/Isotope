"""Supervisor capacity-calling command path."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any, Mapping

from isotope.agents.scheduler.capacity_graph import (
    capacity_graph_node_from_call_selection,
    build_capacity_graph,
    resolve_ready_capacity_plan,
)
from isotope.capabilities.runner import CapabilityRunner
from isotope.llm.capacity_calling import CapacityCallingProvider, select_capacity_call
from isotope.llm.pool import PoolEntry, resolve_pool_entries_from_env
from isotope.llm.provider import OpenAICompatibleChatProvider, Transport, LLMResponse
from isotope.runtime.in_process import InProcessServer


DEFAULT_CAPACITY_PLAN_STATE_ROOT = (
    Path.home() / ".codex" / "supervisor" / "capacity-loop-runs"
)


class PooledCapacityCallingProvider:
    """Small provider adapter for capacity calling over the shared TOML pool."""

    provider = "pooled"
    model = "pooled"

    def __init__(
        self,
        *,
        entries: tuple[PoolEntry, ...],
        timeout: int = 60,
        transport: Transport | None = None,
    ) -> None:
        if not entries:
            raise ValueError("entries must not be empty")
        self._entries = entries
        self._timeout = timeout
        self._transport = transport

    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 512,
    ) -> LLMResponse:
        failures: list[str] = []
        for entry in self._entries:
            try:
                return OpenAICompatibleChatProvider(
                    provider=entry.provider,
                    api_key=entry.api_key,
                    base_url=entry.base_url,
                    model=entry.model,
                    timeout=self._timeout,
                    transport=self._transport,
                ).generate(messages, max_tokens=entry.max_tokens or max_tokens)
            except Exception as exc:
                failures.append(f"{entry.provider}:{type(exc).__name__}")
        raise ValueError(
            "All capacity-calling pool entries failed: " + ", ".join(failures)
        )


def resolve_capacity_calling_provider_from_env(
    environ: Mapping[str, str] | None = None,
    *,
    transport: Transport | None = None,
) -> PooledCapacityCallingProvider:
    env = os.environ if environ is None else environ
    entries = resolve_pool_entries_from_env(
        env,
        env_var="SUPERVISOR_LLM_POOL_TOML_FILES",
        default_paths=(Path(__file__).resolve().parents[1] / "supervisor_llm_pool.toml",),
    )
    if not entries:
        raise ValueError(
            "No capacity-calling LLM pool entries found. "
            "Check SUPERVISOR_LLM_POOL_TOML_FILES or supervisor_llm_pool.toml."
        )
    return PooledCapacityCallingProvider(entries=entries, transport=transport)


def build_supervisor_capacity_plan(
    *,
    goal: str,
    provider: CapacityCallingProvider,
    state_root: Path | str | None = None,
    execute_agent_loop: bool = False,
    runner: CapabilityRunner | None = None,
) -> dict[str, Any]:
    """Plan one Supervisor capacity call, optionally proving the agent-loop path."""
    capacity_runner = runner or CapabilityRunner()
    offered_capacities = _capacity_manifests_from_runner(capacity_runner)
    if not offered_capacities:
        return _no_offered_capacities_plan(
            goal=goal,
            execute_agent_loop=execute_agent_loop,
        )
    selection = select_capacity_call(
        provider,
        goal=goal,
        capacities=offered_capacities,
    )
    if selection.status != "ready_to_call":
        selection_payload = selection.to_dict()
        return {
            "status": "needs_input",
            "status_reason": "needs_input",
            "capacity_blocked_reason": _capacity_blocked_reason(
                status_reason="needs_input",
                launch_plan=None,
            ),
            "kind": "supervisor_capacity_plan",
            "goal": goal,
            "selection": selection_payload,
            "capacity_graph": _blocked_capacity_graph(selection),
            "capability_launch_plan": None,
            "agent_loop": None,
            "supervisor_decision": _capacity_supervisor_decision(
                status_reason="needs_input",
                selection=selection_payload,
                launch_plan=None,
            ),
            "safety": _capacity_plan_safety(execute_agent_loop=execute_agent_loop),
        }
    node = capacity_graph_node_from_call_selection(selection)
    graph = build_capacity_graph([node])
    capacity_plan = resolve_ready_capacity_plan(graph, states={})
    launch_plan = capacity_runner.plan_capability_run(
        selection.capacity_id,
        inputs=selection.arguments,
    )
    agent_loop = None
    if execute_agent_loop and launch_plan.get("can_launch") is True:
        agent_loop = _execute_agent_loop_capacity_step(
            goal=goal,
            capability_id=selection.capacity_id,
            inputs=selection.arguments,
            state_root=(
                Path(state_root)
                if state_root is not None
                else DEFAULT_CAPACITY_PLAN_STATE_ROOT
            ),
        )
    selection_payload = selection.to_dict()
    status_reason = (
        "ready" if launch_plan.get("can_launch") is True else "not_launchable"
    )
    payload = {
        "status": "ok" if launch_plan.get("can_launch") is True else "blocked",
        "status_reason": status_reason,
        "kind": "supervisor_capacity_plan",
        "goal": goal,
        "selection": selection_payload,
        "capacity_graph": capacity_plan.to_dict(),
        "capability_launch_plan": launch_plan,
        "agent_loop": agent_loop,
        "supervisor_decision": _capacity_supervisor_decision(
            status_reason=status_reason,
            selection=selection_payload,
            launch_plan=launch_plan,
        ),
        "safety": _capacity_plan_safety(execute_agent_loop=execute_agent_loop),
    }
    blocked_reason = _capacity_blocked_reason(
        status_reason=status_reason,
        launch_plan=launch_plan,
    )
    if blocked_reason is not None:
        payload["capacity_blocked_reason"] = blocked_reason
    return payload


def handle_capacity_command(
    args: Any,
    *,
    api: Any | None = None,
    provider: CapacityCallingProvider | None = None,
    runner: CapabilityRunner | None = None,
) -> int:
    if args.capacity_command != "plan":
        raise ValueError(f"unsupported capacity command: {args.capacity_command}")
    active_provider = provider or resolve_capacity_calling_provider_from_env()
    payload = build_supervisor_capacity_plan(
        goal=args.goal,
        provider=active_provider,
        runner=runner,
        state_root=args.state_root,
        execute_agent_loop=args.execute_agent_loop,
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        _print_capacity_plan_plain(payload)
    return 0


def execute_capacity_action(
    args: Any,
    action: Mapping[str, Any],
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    capacity_id = action.get("capacity_id")
    if not isinstance(capacity_id, str) or not capacity_id:
        raise ValueError("call_capacity requires capacity_id")
    if _ready_capacity_decision(payload.get("capacity_decisions"), capacity_id) is None:
        return {
            "kind": "call_capacity",
            "capacity_id": capacity_id,
            "skipped": True,
            "reason": "capacity decision not ready",
        }
    spec = _capacity_call_spec(payload.get("capacity_call_specs"), capacity_id)
    if spec is None:
        return {
            "kind": "call_capacity",
            "capacity_id": capacity_id,
            "skipped": True,
            "reason": "capacity call spec unavailable",
        }
    goal = spec.get("goal")
    inputs = spec.get("inputs")
    state_root = spec.get("state_root")
    agent_loop = _execute_agent_loop_capacity_step(
        goal=goal if isinstance(goal, str) and goal else f"Call {capacity_id}",
        capability_id=capacity_id,
        inputs=inputs if isinstance(inputs, Mapping) else {},
        state_root=(
            Path(state_root)
            if isinstance(state_root, str) and state_root
            else Path(args.codex_home) / "supervisor" / "capacity-loop-runs"
        ),
    )
    return {
        "kind": "call_capacity",
        "capacity_id": capacity_id,
        "goal": goal if isinstance(goal, str) and goal else f"Call {capacity_id}",
        "agent_loop": agent_loop,
    }


def loop_capacity_decision_payload(
    args: Any,
    *,
    active_goals: list[dict[str, Any]],
    explicit_goal: str | None,
    api: Any | None = None,
) -> dict[str, Any] | None:
    if api is None:
        from isotope.features.supervisor import runner as api

    if not getattr(args, "capacity_decisions", False):
        return None
    goal = capacity_decision_goal(
        explicit_goal=explicit_goal,
        active_goals=active_goals,
    )
    if goal is None:
        return {
            "status": "skipped",
            "reason": "missing_goal",
            "capacity_decisions": [],
            "capacity_call_specs": [],
        }
    try:
        provider = api.resolve_capacity_calling_provider_from_env()
        plan = api.build_supervisor_capacity_plan(
            goal=goal,
            provider=provider,
            execute_agent_loop=False,
        )
    except Exception as exc:
        return {
            "status": "unavailable",
            "reason": str(exc),
            "error_type": type(exc).__name__,
            "capacity_decisions": [],
            "capacity_call_specs": [],
        }
    decision = plan.get("supervisor_decision")
    decisions = [decision] if isinstance(decision, dict) else []
    payload = {
        "status": plan.get("status", "unknown"),
        "reason": plan.get("status_reason"),
        "goal": goal,
        "capacity_decisions": decisions,
        "capacity_call_specs": capacity_call_specs(plan, goal=goal),
    }
    if plan.get("status_reason") == "no_offered_capacities":
        payload["capacity_blocked_reason"] = "no_offered_capacities"
    return payload


def capacity_call_specs(plan: dict[str, Any], *, goal: str) -> list[dict[str, Any]]:
    if plan.get("status") != "ok" or plan.get("status_reason") != "ready":
        return []
    decision = plan.get("supervisor_decision")
    if not isinstance(decision, dict):
        return []
    if decision.get("next_action") != "call_capacity":
        return []
    if decision.get("can_execute_agent_loop") is not True:
        return []
    capacity_id = decision.get("capacity_id")
    if not isinstance(capacity_id, str) or not capacity_id:
        return []
    launch_plan = plan.get("capability_launch_plan")
    if isinstance(launch_plan, Mapping):
        if (
            launch_plan.get("capability_id") != capacity_id
            or launch_plan.get("can_launch") is not True
        ):
            return []
    selection = plan.get("selection")
    if not isinstance(selection, dict) or selection.get("capacity_id") != capacity_id:
        return []
    arguments = selection.get("arguments")
    inputs = dict(arguments) if isinstance(arguments, dict) else {}
    return [{"capacity_id": capacity_id, "goal": goal, "inputs": inputs}]


def capacity_decision_goal(
    *,
    explicit_goal: str | None,
    active_goals: list[dict[str, Any]],
) -> str | None:
    if explicit_goal is not None:
        return explicit_goal
    for goal in active_goals:
        value = goal.get("goal")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _capacity_call_spec(
    specs: Any,
    capacity_id: str,
) -> Mapping[str, Any] | None:
    if not isinstance(specs, list):
        return None
    for spec in specs:
        if isinstance(spec, Mapping) and spec.get("capacity_id") == capacity_id:
            return spec
    return None


def _ready_capacity_decision(
    decisions: Any,
    capacity_id: str,
) -> Mapping[str, Any] | None:
    if not isinstance(decisions, list):
        return None
    for decision in decisions:
        if not isinstance(decision, Mapping):
            continue
        if decision.get("capacity_id") != capacity_id:
            continue
        if decision.get("next_action") != "call_capacity":
            continue
        if decision.get("can_execute_agent_loop") is not True:
            continue
        return decision
    return None


def _execute_agent_loop_capacity_step(
    *,
    goal: str,
    capability_id: str,
    inputs: Mapping[str, Any],
    state_root: Path,
) -> dict[str, Any]:
    server = InProcessServer(state_root)
    session = server.create_session()
    run = server.create_run(session["session_id"], goal)
    control = server.get_agent_loop_control(run["run_id"])
    step_request = {
        "step": "call_capability",
        "capability_id": capability_id,
        "inputs": copy.deepcopy(dict(inputs)),
    }
    planner_run_id = f"supervisor_capacity:{capability_id}"
    planner_output = {
        "planner_run_id": planner_run_id,
        "basis": {
            "run_id": control["run_id"],
            "last_event_id": control["last_event_id"],
        },
        "decision": {
            "step": "call_capability",
            "request": step_request,
        },
    }
    tick_result = server.run_agent_loop_tick(
        run["run_id"],
        planner_output,
        tick_budget={
            "max_ticks": 1,
            "ticks_used": 0,
            "budget_basis": planner_run_id,
        },
    )
    step_result = tick_result["planner_result"]["step_result"]
    tick_policy_after = server.get_agent_loop_tick_policy(run["run_id"])
    return {
        "executed": True,
        "state_root": str(state_root),
        "session_id": session["session_id"],
        "run_id": run["run_id"],
        "tick_policy_before": tick_result["before_policy"],
        "planner_output_summary": {
            "planner_run_id": planner_run_id,
            "selected_step": "call_capability",
            "capability_id": capability_id,
        },
        "tick_result": tick_result,
        "step_request": step_request,
        "step_result": step_result,
        "tick_policy_after": tick_policy_after,
        "handoff": _agent_loop_handoff_summary(
            tick_result["before_policy"],
            tick_policy_after,
        ),
    }


def _agent_loop_handoff_summary(
    tick_policy_before: Mapping[str, Any],
    tick_policy_after: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "initial_next_tick_kind": tick_policy_before.get("max_next_tick_kind"),
        "post_step_phase": tick_policy_after.get("phase"),
        "post_step_should_continue": tick_policy_after.get("should_continue"),
        "post_step_stop_reason": tick_policy_after.get("must_stop_reason"),
    }


def _capacity_supervisor_decision(
    *,
    status_reason: str,
    selection: Mapping[str, Any],
    launch_plan: Mapping[str, Any] | None,
) -> dict[str, Any]:
    capacity_id = selection.get("capacity_id")
    return {
        "kind": "supervisor_capacity_decision",
        "next_action": _capacity_decision_next_action(status_reason),
        "reason": status_reason,
        "capacity_id": capacity_id if isinstance(capacity_id, str) else "unknown",
        "can_execute_agent_loop": status_reason == "ready",
        "missing_inputs": _string_list(selection.get("missing_inputs")),
        "blocking_reasons": _string_list(
            launch_plan.get("blocking_reasons") if launch_plan is not None else None
        ),
    }


def _capacity_decision_next_action(status_reason: str) -> str:
    if status_reason == "ready":
        return "call_capacity"
    if status_reason == "needs_input":
        return "request_input"
    if status_reason in {"not_launchable", "no_offered_capacities"}:
        return "blocked"
    return "wait"


def _capacity_blocked_reason(
    *,
    status_reason: str,
    launch_plan: Mapping[str, Any] | None,
) -> str | None:
    if status_reason == "ready":
        return None
    if status_reason == "needs_input":
        return "missing_inputs"
    if status_reason == "no_offered_capacities":
        return "no_offered_capacities"
    if status_reason == "not_launchable":
        blocking_reasons = _string_list(
            launch_plan.get("blocking_reasons") if launch_plan is not None else None
        )
        return blocking_reasons[0] if blocking_reasons else "not_launchable"
    return status_reason


def _capacity_manifests_from_runner(
    capacity_runner: CapabilityRunner,
) -> list[dict[str, Any]]:
    manifests: list[dict[str, Any]] = []
    for capability in capacity_runner.list_capabilities():
        capability_id = capability.get("capability_id")
        if not isinstance(capability_id, str) or not capability_id:
            continue
        launch_plan = capacity_runner.plan_capability_run(capability_id, inputs={})
        if not _can_offer_capacity_manifest(launch_plan):
            continue
        manifests.append(
            {
                "capacity_id": capability_id,
                "title": capability.get("title"),
                "description": capability.get("description"),
                "domain_tags": capability.get("domain_tags") or [],
                "input_contract": capability.get("input_contract") or {},
            }
        )
    return manifests


def _can_offer_capacity_manifest(launch_plan: Mapping[str, Any]) -> bool:
    if launch_plan.get("can_launch") is True:
        return True
    return launch_plan.get("status") == "missing_inputs"


def _no_offered_capacities_plan(
    *,
    goal: str,
    execute_agent_loop: bool,
) -> dict[str, Any]:
    status_reason = "no_offered_capacities"
    return {
        "status": "blocked",
        "status_reason": status_reason,
        "capacity_blocked_reason": status_reason,
        "kind": "supervisor_capacity_plan",
        "goal": goal,
        "selection": None,
        "capacity_graph": {
            "kind": "capacity_graph_plan",
            "status": "blocked",
            "summary": {"ready": 0, "blocked": 0},
            "calls": [],
        },
        "capability_launch_plan": None,
        "agent_loop": None,
        "supervisor_decision": _capacity_supervisor_decision(
            status_reason=status_reason,
            selection={"capacity_id": "unknown", "missing_inputs": []},
            launch_plan={"blocking_reasons": [status_reason]},
        ),
        "safety": _capacity_plan_safety(execute_agent_loop=execute_agent_loop),
    }


def _blocked_capacity_graph(selection: Any) -> dict[str, Any]:
    return {
        "kind": "capacity_graph_plan",
        "status": "blocked",
        "summary": {
            "ready": 0,
            "blocked": 1,
        },
        "calls": [],
        "blocked": [
            {
                "node_id": selection.capacity_id.replace(".", "-"),
                "capacity_id": selection.capacity_id,
                "reason": selection.status,
            }
        ],
    }


def _capacity_plan_safety(*, execute_agent_loop: bool) -> dict[str, Any]:
    return {
        "default_mode": "plan_only",
        "execute_agent_loop": execute_agent_loop,
        "note": "默认只生成能力调用计划；缺少输入时停在 plan 层；显式开启 execute_agent_loop 才运行 allowlist 低风险能力。",
    }


def _print_capacity_plan_plain(payload: Mapping[str, Any]) -> None:
    selection = payload.get("selection") if isinstance(payload, Mapping) else {}
    launch_plan = (
        payload.get("capability_launch_plan") if isinstance(payload, Mapping) else {}
    )
    print("Supervisor capacity plan")
    capacity_id = (
        selection.get("capacity_id") if isinstance(selection, Mapping) else "unknown"
    )
    selection_status = (
        selection.get("status") if isinstance(selection, Mapping) else "unknown"
    )
    launch_status = (
        launch_plan.get("status") if isinstance(launch_plan, Mapping) else "unknown"
    )
    status_reason = payload.get("status_reason", "unknown")
    print(f"capacity_id: {capacity_id}")
    print(f"selection_status: {selection_status}")
    print(f"status_reason: {status_reason}")
    print(f"launch_status: {launch_status}")
    supervisor_decision = payload.get("supervisor_decision")
    if isinstance(supervisor_decision, Mapping):
        print(
            "supervisor_decision_next_action: "
            f"{supervisor_decision.get('next_action')}"
        )
    _print_capacity_blockers(payload, selection=selection, launch_plan=launch_plan)
    print(f"agent_loop_executed: {bool(payload.get('agent_loop'))}")
    agent_loop = payload.get("agent_loop")
    handoff = agent_loop.get("handoff") if isinstance(agent_loop, Mapping) else None
    if isinstance(handoff, Mapping):
        print(f"agent_loop_next_tick_kind: {handoff.get('initial_next_tick_kind')}")
        print(f"agent_loop_post_step_phase: {handoff.get('post_step_phase')}")
        print(
            "agent_loop_post_step_should_continue: "
            f"{handoff.get('post_step_should_continue')}"
        )
        print(f"agent_loop_post_step_stop_reason: {handoff.get('post_step_stop_reason')}")


def _print_capacity_blockers(
    payload: Mapping[str, Any],
    *,
    selection: Any,
    launch_plan: Any,
) -> None:
    if payload.get("status_reason") == "no_offered_capacities":
        print("capacity_blocked_reason: no_offered_capacities")
    if payload.get("status_reason") == "needs_input" and isinstance(selection, Mapping):
        missing_inputs = selection.get("missing_inputs")
        if isinstance(missing_inputs, list) and missing_inputs:
            print("capacity_blocked_reason: missing_inputs")
            print(f"capacity_missing_inputs: {_comma_join_strings(missing_inputs)}")
    if payload.get("status_reason") == "not_launchable" and isinstance(launch_plan, Mapping):
        blocking_reasons = launch_plan.get("blocking_reasons")
        if isinstance(blocking_reasons, list) and blocking_reasons:
            print(f"launch_blocking_reasons: {_comma_join_strings(blocking_reasons)}")


def _comma_join_strings(values: list[Any]) -> str:
    return ", ".join(str(value) for value in values if isinstance(value, str))


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]
