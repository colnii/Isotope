from __future__ import annotations

from isotope.features.supervisor.agent_group.runtime import AgentGroupRuntime
from isotope.features.supervisor.state.projection import build_supervisor_state_snapshot


def test_supervisor_state_snapshot_exposes_agent_group_summary(tmp_path):
    runtime = AgentGroupRuntime(tmp_path)
    runtime.create_group(
        title="Feature group",
        goal="Discuss group chat.",
        member_specs=[{"name": "planner", "role": "Plan work.", "goal": "Find steps."}],
        initial_message="Start.",
    )

    snapshot = build_supervisor_state_snapshot(codex_home=tmp_path)

    assert snapshot["summary"]["agent_groups"] == 1
    assert snapshot["agent_groups"]["total"] == 1
    assert snapshot["agent_groups"]["recent"][0]["title"] == "Feature group"
