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
    capabilities = capacity_runner.list_capabilities()
    selection = select_capacity_call(
        provider,
        goal=goal,
        capacities=_capacity_manifests_from_capabilities(capabilities),
    )
    if selection.status != "ready_to_call":
        return {
            "status": "needs_input",
            "status_reason": "needs_input",
            "kind": "supervisor_capacity_plan",
            "goal": goal,
            "selection": selection.to_dict(),
            "capacity_graph": _blocked_capacity_graph(selection),
            "capability_launch_plan": None,
            "agent_loop": None,
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
    return {
        "status": "ok" if launch_plan.get("can_launch") is True else "blocked",
        "status_reason": (
            "ready" if launch_plan.get("can_launch") is True else "not_launchable"
        ),
        "kind": "supervisor_capacity_plan",
        "goal": goal,
        "selection": selection.to_dict(),
        "capacity_graph": capacity_plan.to_dict(),
        "capability_launch_plan": launch_plan,
        "agent_loop": agent_loop,
        "safety": _capacity_plan_safety(execute_agent_loop=execute_agent_loop),
    }


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
    tick_policy_before = server.get_agent_loop_tick_policy(run["run_id"])
    step_request = {
        "step": "call_capability",
        "capability_id": capability_id,
        "inputs": copy.deepcopy(dict(inputs)),
    }
    step_result = server.run_agent_loop_step(run["run_id"], step_request)
    tick_policy_after = server.get_agent_loop_tick_policy(run["run_id"])
    return {
        "executed": True,
        "state_root": str(state_root),
        "session_id": session["session_id"],
        "run_id": run["run_id"],
        "tick_policy_before": tick_policy_before,
        "step_request": step_request,
        "step_result": step_result,
        "tick_policy_after": tick_policy_after,
        "handoff": _agent_loop_handoff_summary(tick_policy_before, tick_policy_after),
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


def _capacity_manifests_from_capabilities(
    capabilities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    manifests: list[dict[str, Any]] = []
    for capability in capabilities:
        capability_id = capability.get("capability_id")
        if not isinstance(capability_id, str) or not capability_id:
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
