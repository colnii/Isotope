"""Supervisor capacity-calling command path."""

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from isotope.agents.scheduler.capacity_graph import (
    capacity_graph_node_from_call_selection,
    build_capacity_graph,
    resolve_ready_capacity_plan,
)
from isotope.capabilities.runner import CapabilityRunner
from isotope.capabilities.supervisor import SUPERVISOR_CODEX_OPERATION_CAPABILITY
from isotope.features.supervisor.commands.capacity.capacity_rendering import (
    print_capacity_plan_plain,
)
from isotope.features.supervisor.commands.capacity.capacity_result import (
    agent_loop_handoff_result,
    agent_loop_json_result,
)
from isotope.llm.capacity_calling import CapacityCallingProvider, select_capacity_call
from isotope.llm.pool import PoolEntry, resolve_pool_entries_from_env
from isotope.llm.provider import (
    LLMResponse,
    Transport,
    create_chat_provider_from_pool_entry,
)
from isotope.platform.schemas.input_contract import (
    contract_properties,
    missing_required_input_keys,
    required_contract_keys,
)
from isotope.platform.schemas.actions import ActionExecution
from isotope.platform.schemas.memory import MemoryRecord
from isotope.platform.state.memory_store import FileMemoryStore
from isotope.runtime.in_process import InProcessServer


DEFAULT_CAPACITY_PLAN_STATE_ROOT = (
    Path.home() / ".codex" / "supervisor" / "capacity-loop-runs"
)

_print_capacity_plan_plain = print_capacity_plan_plain


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
        codex_process_runner: Callable[..., Any] = subprocess.run,
        codex_executable_resolver: Callable[[str], str | None] = shutil.which,
    ) -> None:
        if not entries:
            raise ValueError("entries must not be empty")
        self._entries = entries
        self._timeout = timeout
        self._transport = transport
        self._codex_process_runner = codex_process_runner
        self._codex_executable_resolver = codex_executable_resolver

    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 512,
    ) -> LLMResponse:
        failures: list[str] = []
        for entry in self._entries:
            try:
                provider = create_chat_provider_from_pool_entry(
                    entry,
                    timeout=self._timeout,
                    transport=self._transport,
                    codex_process_runner=self._codex_process_runner,
                    codex_executable_resolver=self._codex_executable_resolver,
                )
                return provider.generate(messages, max_tokens=entry.max_tokens or max_tokens)
            except Exception as exc:
                failures.append(f"{entry.provider}:{type(exc).__name__}")
        raise ValueError(
            "All capacity-calling pool entries failed: " + ", ".join(failures)
        )


def resolve_capacity_calling_provider_from_env(
    environ: Mapping[str, str] | None = None,
    *,
    timeout: int | None = None,
    transport: Transport | None = None,
    codex_process_runner: Callable[..., Any] = subprocess.run,
    codex_executable_resolver: Callable[[str], str | None] = shutil.which,
) -> PooledCapacityCallingProvider:
    env = os.environ if environ is None else environ
    entries = resolve_pool_entries_from_env(
        env,
        env_var="SUPERVISOR_LLM_POOL_TOML_FILES",
        default_paths=(Path(__file__).resolve().parents[2] / "supervisor_llm_pool.toml",),
    )
    if not entries:
        raise ValueError(
            "No capacity-calling LLM pool entries found. "
            "Check SUPERVISOR_LLM_POOL_TOML_FILES or supervisor_llm_pool.toml."
        )
    return PooledCapacityCallingProvider(
        entries=entries,
        timeout=timeout or 60,
        transport=transport,
        codex_process_runner=codex_process_runner,
        codex_executable_resolver=codex_executable_resolver,
    )


def build_supervisor_capacity_plan(
    *,
    goal: str,
    provider: CapacityCallingProvider,
    state_root: Path | str | None = None,
    execute_agent_loop: bool = False,
    runner: CapabilityRunner | None = None,
    input_defaults: Mapping[str, Any] | None = None,
    allow_no_capacity: bool = False,
    offered_capacities: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Plan one Supervisor capacity call, optionally proving the agent-loop path."""
    capacity_runner = runner or CapabilityRunner()
    active_offered_capacities = (
        offered_capacities
        if offered_capacities is not None
        else _capacity_manifests_from_runner(capacity_runner)
    )
    if not active_offered_capacities:
        return _no_offered_capacities_plan(
            goal=goal,
            execute_agent_loop=execute_agent_loop,
        )
    selection = select_capacity_call(
        provider,
        goal=goal,
        capacities=active_offered_capacities,
        allow_no_capacity=allow_no_capacity,
    )
    selection_payload = _selection_with_input_defaults(
        selection.to_dict(),
        offered_capacities=active_offered_capacities,
        input_defaults=input_defaults,
    )
    if selection_payload["status"] == "no_capacity":
        payload = {
            "status": "skipped",
            "status_reason": "no_capacity",
            "kind": "supervisor_capacity_plan",
            "goal": goal,
            "selection": selection_payload,
            "capacity_graph": {
                "kind": "capacity_graph_plan",
                "status": "skipped",
                "summary": {"ready": 0, "blocked": 0},
                "calls": [],
            },
            "capability_launch_plan": None,
            "agent_loop": None,
            "supervisor_decision": _capacity_supervisor_decision(
                status_reason="no_capacity",
                selection=selection_payload,
                launch_plan=None,
            ),
            "safety": _capacity_plan_safety(execute_agent_loop=execute_agent_loop),
        }
        payload["agent_loop_result"] = agent_loop_json_result(payload)
        return payload
    if selection_payload["status"] != "ready_to_call":
        payload = {
            "status": "needs_input",
            "status_reason": "needs_input",
            "capacity_blocked_reason": _capacity_blocked_reason(
                status_reason="needs_input",
                launch_plan=None,
            ),
            "kind": "supervisor_capacity_plan",
            "goal": goal,
            "selection": selection_payload,
            "capacity_graph": _blocked_capacity_graph(selection_payload),
            "capability_launch_plan": None,
            "agent_loop": None,
            "supervisor_decision": _capacity_supervisor_decision(
                status_reason="needs_input",
                selection=selection_payload,
                launch_plan=None,
            ),
            "safety": _capacity_plan_safety(execute_agent_loop=execute_agent_loop),
        }
        payload["agent_loop_result"] = agent_loop_json_result(payload)
        return payload
    node = capacity_graph_node_from_call_selection(selection_payload)
    graph = build_capacity_graph([node])
    capacity_plan = resolve_ready_capacity_plan(graph, states={})
    capacity_id = selection_payload["capacity_id"]
    arguments = selection_payload["arguments"]
    launch_plan = capacity_runner.plan_capability_run(
        capacity_id,
        inputs=arguments,
    )
    agent_loop = None
    if execute_agent_loop and launch_plan.get("can_launch") is True:
        agent_loop = _execute_agent_loop_capacity_step(
            goal=goal,
            capability_id=capacity_id,
            inputs=arguments,
            state_root=(
                Path(state_root)
                if state_root is not None
                else DEFAULT_CAPACITY_PLAN_STATE_ROOT
            ),
        )
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
    payload["agent_loop_result"] = agent_loop_json_result(payload)
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
        input_defaults=_supervisor_capacity_input_defaults(args),
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print_capacity_plan_plain(payload)
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
    agent_loop_result = agent_loop_json_result({"agent_loop": agent_loop})
    _record_capacity_call_memory(
        codex_home=Path(args.codex_home),
        worker_name=getattr(args, "name", None),
        capacity_id=capacity_id,
        agent_loop=agent_loop,
        agent_loop_result=agent_loop_result,
    )
    return {
        "kind": "call_capacity",
        "capacity_id": capacity_id,
        "goal": goal if isinstance(goal, str) and goal else f"Call {capacity_id}",
        "agent_loop": agent_loop,
        "agent_loop_result": agent_loop_result,
    }


def execute_codex_operation_via_agent_loop(
    *,
    goal: str,
    operation: str,
    inputs: Mapping[str, Any],
    state_root: Path | str,
) -> dict[str, Any]:
    if not isinstance(goal, str) or not goal.strip():
        raise ValueError("goal must not be empty")
    if not isinstance(operation, str) or not operation.strip():
        raise ValueError("operation must not be empty")
    if not isinstance(inputs, Mapping):
        raise ValueError("inputs must be a mapping")
    capability_inputs = {"operation": operation, **copy.deepcopy(dict(inputs))}
    agent_loop = _execute_agent_loop_capacity_step(
        goal=goal.strip(),
        capability_id=SUPERVISOR_CODEX_OPERATION_CAPABILITY,
        inputs=capability_inputs,
        state_root=Path(state_root),
    )
    agent_loop_result = agent_loop_json_result({"agent_loop": agent_loop})
    return {
        "kind": "call_capacity",
        "capacity_id": SUPERVISOR_CODEX_OPERATION_CAPABILITY,
        "operation": operation,
        "goal": goal.strip(),
        "agent_loop": agent_loop,
        "agent_loop_result": agent_loop_result,
    }


def execute_codex_operation_action(
    args: Any,
    action: Mapping[str, Any],
) -> dict[str, Any]:
    kind = action.get("kind")
    if kind == "request_context":
        cwd = action.get("cwd")
        query = action.get("query")
        if not isinstance(cwd, str) or not cwd.strip():
            raise ValueError("cwd is required for request_context")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query is required for request_context")
        inputs: dict[str, Any] = {
            "state_root": str(Path(args.codex_home)),
            "cwd": cwd,
            "query": query,
        }
        max_results = action.get("max_results")
        if isinstance(max_results, int) and not isinstance(max_results, bool):
            inputs["max_results"] = max_results
        return execute_codex_operation_via_agent_loop(
            goal=f"Request context: {query}",
            operation="request_context",
            inputs=inputs,
            state_root=Path(args.codex_home) / "supervisor" / "capacity-loop-runs",
        )
    raise ValueError(f"unsupported codex operation action: {kind}")


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
            input_defaults=_supervisor_capacity_input_defaults(args),
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
    blocked_reason = plan.get("capacity_blocked_reason")
    if blocked_reason is None and plan.get("status_reason") == "no_offered_capacities":
        blocked_reason = "no_offered_capacities"
    if isinstance(blocked_reason, str) and blocked_reason:
        payload["capacity_blocked_reason"] = blocked_reason
    agent_loop_result = plan.get("agent_loop_result")
    if isinstance(agent_loop_result, dict):
        payload["agent_loop_result"] = copy.deepcopy(agent_loop_result)
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


def _supervisor_capacity_input_defaults(args: Any) -> dict[str, Any]:
    codex_home = getattr(args, "codex_home", None)
    if not isinstance(codex_home, str) or not codex_home:
        return {}
    root = str(Path(codex_home))
    return {"state_root": root, "root": root}


def _record_capacity_call_memory(
    *,
    codex_home: Path,
    worker_name: Any,
    capacity_id: str,
    agent_loop: Mapping[str, Any],
    agent_loop_result: Mapping[str, Any],
) -> None:
    worker = (
        worker_name if isinstance(worker_name, str) and worker_name else "supervisor"
    )
    run_id = agent_loop.get("run_id")
    memory_id = "mem_capacity_" + uuid.uuid4().hex[:12]
    execution_id = "exec_capacity_memory_" + uuid.uuid4().hex[:12]
    record = MemoryRecord(
        memory_id=memory_id,
        scope="run",
        content={
            "kind": "capacity_call",
            "worker_name": worker,
            "capacity_id": capacity_id,
            "agent_loop_result": dict(agent_loop_result),
        },
        summary=f"{worker} called {capacity_id} via agent loop.",
        source_refs=[],
        provenance={
            "run_id": (
                run_id if isinstance(run_id, str) and run_id else "supervisor_capacity"
            ),
            "execution_id": execution_id,
            "action_type": "capacity_call",
        },
        created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        supersedes=[],
        quality="verified",
    )
    execution = ActionExecution(
        execution_id=execution_id,
        proposal_id="prop_capacity_memory_" + uuid.uuid4().hex[:12],
        decision_id="dec_capacity_memory_" + uuid.uuid4().hex[:12],
        action_type="write_memory",
        status="completed",
        effective_grants_snapshot={"tools": ["write_memory"]},
    )
    FileMemoryStore(codex_home).save_record(
        record,
        execution=execution,
        grants={"tools": ["write_memory"]},
    )


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
        "planner_output": {
            "planner_run_id": planner_run_id,
            "selected_step": "call_capability",
            "capability_id": capability_id,
        },
        "tick_result": tick_result,
        "step_request": step_request,
        "step_result": step_result,
        "tick_policy_after": tick_policy_after,
        "handoff": agent_loop_handoff_result(
            tick_result["before_policy"],
            tick_policy_after,
        ),
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
    payload = {
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
    payload["agent_loop_result"] = agent_loop_json_result(payload)
    return payload


def _blocked_capacity_graph(selection: Any) -> dict[str, Any]:
    if isinstance(selection, Mapping):
        capacity_id = selection.get("capacity_id")
        status = selection.get("status")
    else:
        capacity_id = getattr(selection, "capacity_id", None)
        status = getattr(selection, "status", None)
    capacity_id = capacity_id if isinstance(capacity_id, str) else "unknown"
    status = status if isinstance(status, str) else "unknown"
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
                "node_id": capacity_id.replace(".", "-"),
                "capacity_id": capacity_id,
                "reason": status,
            }
        ],
    }


def _selection_with_input_defaults(
    selection: Mapping[str, Any],
    *,
    offered_capacities: list[Mapping[str, Any]],
    input_defaults: Mapping[str, Any] | None,
) -> dict[str, Any]:
    payload = copy.deepcopy(dict(selection))
    if payload.get("status") == "no_capacity":
        payload["arguments"] = {}
        payload["missing_inputs"] = []
        return payload
    capacity = _offered_capacity_by_id(payload.get("capacity_id"), offered_capacities)
    contract = capacity.get("input_contract") if isinstance(capacity, Mapping) else {}
    properties = contract_properties(contract if isinstance(contract, Mapping) else {})
    required_inputs = required_contract_keys(
        contract if isinstance(contract, Mapping) else {}
    )
    arguments = payload.get("arguments")
    if not isinstance(arguments, dict):
        arguments = {}
    defaults = _safe_input_defaults(input_defaults)
    for name, value in defaults.items():
        if name not in arguments and name in properties:
            arguments[name] = value
    payload["arguments"] = arguments
    missing_inputs = missing_required_input_keys(arguments, required_inputs)
    payload["missing_inputs"] = missing_inputs
    payload["status"] = "missing_inputs" if missing_inputs else "ready_to_call"
    return payload


def _offered_capacity_by_id(
    capacity_id: Any,
    offered_capacities: list[Mapping[str, Any]],
) -> Mapping[str, Any]:
    for capability in offered_capacities:
        if (
            isinstance(capability, Mapping)
            and capability.get("capacity_id") == capacity_id
        ):
            return capability
    return {}


def _safe_input_defaults(input_defaults: Mapping[str, Any] | None) -> dict[str, Any]:
    if input_defaults is None:
        return {}
    if not isinstance(input_defaults, Mapping):
        raise ValueError("input_defaults must be a mapping")
    return {
        key: value
        for key, value in input_defaults.items()
        if isinstance(key, str) and value not in (None, "")
    }


def _capacity_plan_safety(*, execute_agent_loop: bool) -> dict[str, Any]:
    return {
        "default_mode": "decision_path",
        "execute_agent_loop": execute_agent_loop,
        "note": "按能力契约生成调用决策；输入齐备且执行路径开启时进入 agent loop，缺少输入时返回 request_input。",
    }


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]
