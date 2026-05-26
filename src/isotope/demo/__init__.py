"""Developer demo entrypoint for the Isotope application slices."""

from __future__ import annotations

import argparse
import json
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .format.demo_format import _format_plain_text, _format_trace
from .demo_common import _deferred_status, _latest_action_status
from .agent_loop.demo_agent_loop_scenarios import (
    _run_agent_loop_friction_spike,
    _run_agent_loop_planner_adapter_spike,
)
from .agent_loop.demo_agent_loop_matrix_scenarios import (
    _run_agent_loop_planner_matrix_spike,
    _run_agent_loop_planner_restart_pause_spike,
)
from .agent_loop.demo_agent_loop_tick_scenarios import (
    _run_agent_loop_tick_driver_trace,
    _run_agent_loop_tick_policy_trace,
    _run_supervisor_capacity_handoff_trace,
)
from .agent_loop.demo_agent_loop_validation_scenarios import (
    _run_agent_loop_planner_io_validator_spike,
    _run_agent_loop_planner_validated_runner_spike,
)
from .demo_artifact_review_scenarios import _run_artifact_review_spike
from .demo_review_scenarios import (
    _run_approval_tool_runner_spike,
    _run_external_snapshot_review_spike,
)
from .demo_workspace_scenarios import (
    _run_project_workspace_append_demo,
    _run_project_workspace_demo,
    _run_workbench_ask_demo,
    _run_workbench_demo,
)
from .llm.demo_llm_bridge_scenarios import (
    _run_llm_provider_route_demo,
    _run_model_tool_bridge_demo,
)
from .llm.demo_llm_product_chat_scenarios import _run_llm_product_chat_app_entry_demo
from .llm.demo_llm_terminal_scenarios import _run_llm_terminal_tool_loop_demo
from .llm.demo_llm_tool_result_scenarios import _run_llm_tool_result_loop_demo
from .demo_memory_scenarios import _run_memory_query_smoke_demo
from .demo_terminal_scenarios import _run_terminal_exec_demo
from ..platform.state.checkpoint_store import FileCheckpointStore
from ..interfaces.http import create_http_app
from ..platform.state.projector import RunProjector
from ..runtime.in_process import InProcessServer


def run_demo(root_path: Path | str | None = None, scenario: str = "v0.1") -> dict[str, Any]:
    """Run a deterministic developer demo and return summary metadata."""

    if root_path is None:
        with tempfile.TemporaryDirectory(prefix="isotope-demo-") as temp_root:
            return _run_scenario(Path(temp_root), scenario=scenario)
    return _run_scenario(Path(root_path), scenario=scenario)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run an Isotope developer demo.")
    parser.add_argument(
        "--scenario",
        choices=(
            "v0.1",
            "v0.2",
            "approval-tool-runner",
            "artifact-review",
            "external-snapshot-review",
            "agent-loop-friction",
            "agent-loop-planner-friction",
            "agent-loop-planner-matrix",
            "agent-loop-planner-restart-pause",
            "agent-loop-tick-policy-trace",
            "agent-loop-tick-driver-trace",
            "supervisor-capacity-handoff-trace",
            "agent-loop-planner-io-validator",
            "agent-loop-planner-validated-runner",
            "terminal-exec",
            "model-tool-bridge",
            "llm-provider-route",
            "llm-tool-result-loop",
            "llm-product-chat-app-entry",
            "llm-terminal-tool-loop",
            "memory-query-smoke",
            "workbench",
            "workbench-ask",
            "project-workspace",
            "project-workspace-append",
        ),
        default="v0.1",
        help="demo scenario to run",
    )
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    parser.add_argument("--trace", action="store_true", help="print human-readable execution trace")
    args = parser.parse_args(argv)

    result = run_demo(scenario=args.scenario)
    if args.json:
        print(json.dumps(result, sort_keys=True))
    elif args.trace:
        print(_format_trace(result))
    else:
        print(_format_plain_text(result))
    return 0


def _run_demo(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    checkpoint_store = FileCheckpointStore(root)
    api = InProcessServer(root, checkpoint_store=checkpoint_store)

    session = api.create_session()
    run = api.create_run(session["session_id"], goal="demo deterministic artifact path")
    run_id = run["run_id"]
    api.submit_input(run_id, "hello")

    events = api.get_events(run_id)
    replay_state = RunProjector().rebuild(run_id, api.event_store)
    checkpoint = RunProjector().save_checkpoint(run_id, api.event_store, checkpoint_store)
    checkpoint_state = RunProjector().rebuild_with_checkpoint(run_id, api.event_store, checkpoint_store)
    artifacts = api.artifact_store.list_artifacts(run_id)
    artifact = artifacts[-1]

    artifact_ref = artifact.ref.to_dict()
    checkpoint_artifact_ref = (
        checkpoint_state.artifacts[0]["ref"] if checkpoint_state.artifacts else {}
    )
    replay_ok = asdict(replay_state) == asdict(api.get_run_state(run_id))
    checkpoint_ok = asdict(checkpoint_state) == asdict(replay_state)

    return {
        "session_id": session["session_id"],
        "run_id": run_id,
        "run_status": replay_state.status,
        "action_outcome": _latest_action_status(replay_state.actions),
        "artifact_ref": artifact_ref,
        "artifact_summary": artifact.summary,
        "event_count": len(events),
        "replay_ok": replay_ok,
        "checkpoint_ok": checkpoint_ok,
        "checkpoint_basis_event_id": checkpoint["basis_event_id"],
        "replay_run_status": replay_state.status,
        "checkpoint_run_status": checkpoint_state.status,
        "checkpoint_artifact_ref": checkpoint_artifact_ref,
        "memory_status": "boundary_only",
    }


def _run_scenario(root: Path, *, scenario: str) -> dict[str, Any]:
    if scenario == "v0.1":
        return _run_demo(root)
    if scenario == "v0.2":
        return _run_v0_2_demo(root)
    if scenario == "approval-tool-runner":
        return _run_approval_tool_runner_spike(root)
    if scenario == "artifact-review":
        return _run_artifact_review_spike(root)
    if scenario == "external-snapshot-review":
        return _run_external_snapshot_review_spike(root)
    if scenario == "agent-loop-friction":
        return _run_agent_loop_friction_spike(root)
    if scenario == "agent-loop-planner-friction":
        return _run_agent_loop_planner_adapter_spike(root)
    if scenario == "agent-loop-planner-matrix":
        return _run_agent_loop_planner_matrix_spike(root)
    if scenario == "agent-loop-planner-restart-pause":
        return _run_agent_loop_planner_restart_pause_spike(root)
    if scenario == "agent-loop-tick-policy-trace":
        return _run_agent_loop_tick_policy_trace(root)
    if scenario == "agent-loop-tick-driver-trace":
        return _run_agent_loop_tick_driver_trace(root)
    if scenario == "supervisor-capacity-handoff-trace":
        return _run_supervisor_capacity_handoff_trace(root)
    if scenario == "agent-loop-planner-io-validator":
        return _run_agent_loop_planner_io_validator_spike(root)
    if scenario == "agent-loop-planner-validated-runner":
        return _run_agent_loop_planner_validated_runner_spike(root)
    if scenario == "terminal-exec":
        return _run_terminal_exec_demo(root)
    if scenario == "model-tool-bridge":
        return _run_model_tool_bridge_demo(root)
    if scenario == "llm-provider-route":
        return _run_llm_provider_route_demo(root)
    if scenario == "llm-tool-result-loop":
        return _run_llm_tool_result_loop_demo(root)
    if scenario == "llm-product-chat-app-entry":
        return _run_llm_product_chat_app_entry_demo(root)
    if scenario == "llm-terminal-tool-loop":
        return _run_llm_terminal_tool_loop_demo(root)
    if scenario == "memory-query-smoke":
        return _run_memory_query_smoke_demo(root)
    if scenario == "workbench":
        return _run_workbench_demo(root)
    if scenario == "workbench-ask":
        return _run_workbench_ask_demo(root)
    if scenario == "project-workspace":
        return _run_project_workspace_demo(root)
    if scenario == "project-workspace-append":
        return _run_project_workspace_append_demo(root)
    msg = f"unknown scenario: {scenario!r}"
    raise ValueError(msg)


def _run_v0_2_demo(root: Path) -> dict[str, Any]:
    checkpoint_store = FileCheckpointStore(root)
    api = InProcessServer(root, checkpoint_store=checkpoint_store)
    segment_api = create_http_app(root)

    api._segment_server = segment_api  # type: ignore[attr-defined]

    session = api.create_session()
    run = api.create_run(session["session_id"], goal="demo v0.2 segment trace")
    run_id = run["run_id"]
    submit_month = "2026-04"
    api.submit_input(run_id, f"submit in {submit_month}")
    api.submit_input(run_id, "memory record as segment")
    api.submit_input(run_id, '"memory-mode": "memory-plugin-segment-only"')

    replay_state = RunProjector().rebuild(run_id, api.event_store)
    artifacts = api.artifact_store.list_artifacts(run_id)

    memory_status = _deferred_status(replay_state, run_id, api.memory_store)

    return {
        "session_id": session["session_id"],
        "run_id": run_id,
        "run_status": replay_state.status,
        "action_outcome": _latest_action_status(replay_state.actions),
        "event_count": len(api.event_store.list_events(run_id)),
        "replay_ok": asdict(replay_state) == asdict(api.get_run_state(run_id)),
        "artifact_count": len(artifacts),
        "memory_status": memory_status,
    }
