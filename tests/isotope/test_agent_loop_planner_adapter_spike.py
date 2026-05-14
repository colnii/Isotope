import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
SCENARIO = "agent-loop-planner-friction"

REQUIRED_TEXT_FIELDS = (
    "scenario: agent-loop-planner-friction",
    "planner_adapter_friction_ok: true",
    "planner_adapter_status: deterministic_fixture",
    "planner_decision_count:",
    "kernel_friction_count: 0",
    "private_append_required: false",
    "model_status: not_used",
    "scheduler_status: not_used",
)

REQUIRED_JSON_FIELDS = {
    "scenario",
    "run_status",
    "transport",
    "planner_adapter_friction_ok",
    "planner_adapter_status",
    "planner_input_summary",
    "planner_decisions",
    "planner_decision_count",
    "agent_loop_friction_ok",
    "kernel_friction",
    "private_append_required",
    "replay_ok",
    "checkpoint_ok",
    "model_status",
    "scheduler_status",
    "provider_status",
    "next_development_step",
}

FORBIDDEN_CONTENT_KEYS = {
    "content",
    "artifact_content",
    "full_content",
    "full_text",
    "raw_content",
    "raw_artifact_content",
    "model_prompt",
    "model_response",
}


def _run_demo(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "isotope.demo", *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )


def _run_demo_json(*args: str) -> dict[str, Any]:
    result = _run_demo(*args, "--json")
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _assert_no_forbidden_content_keys(value: Any) -> None:
    if isinstance(value, dict):
        forbidden = FORBIDDEN_CONTENT_KEYS.intersection(value)
        assert forbidden == set()
        for nested in value.values():
            _assert_no_forbidden_content_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_forbidden_content_keys(nested)


def test_planner_adapter_plain_cli_prints_boundary_summary():
    result = _run_demo("--scenario", SCENARIO)

    assert result.returncode == 0, result.stderr
    for field in REQUIRED_TEXT_FIELDS:
        assert field in result.stdout
    assert "real llm" not in result.stdout.lower()


def test_planner_adapter_json_reports_symbolic_decisions_and_no_kernel_gap():
    data = _run_demo_json("--scenario", SCENARIO)

    assert REQUIRED_JSON_FIELDS.issubset(data)
    assert data["scenario"] == SCENARIO
    assert data["planner_adapter_friction_ok"] is True
    assert data["planner_adapter_status"] == "deterministic_fixture"
    assert data["agent_loop_friction_ok"] is True
    assert data["private_append_required"] is False
    assert data["kernel_friction"] == []
    assert data["planner_decision_count"] >= 4
    actions = [decision["action"] for decision in data["planner_decisions"]]
    assert actions[:5] == [
        "create_source_artifact",
        "submit_worker_handoff",
        "submit_approval_gated_action",
        "bind_workspace",
        "resolve_approval",
    ]
    assert data["replay_ok"] is True
    assert data["checkpoint_ok"] is True


def test_planner_adapter_keeps_deferred_integrations_disabled():
    data = _run_demo_json("--scenario", SCENARIO)

    assert data["transport"] == "in_process"
    assert data["model_status"] == "not_used"
    assert data["scheduler_status"] == "not_used"
    assert data["provider_status"] == "not_used"
    assert data.get("network_listener_status", "not_used") == "not_used"
    assert data.get("memory_query_status", "not_enabled") == "not_enabled"


def test_planner_adapter_json_excludes_model_and_artifact_full_content():
    data = _run_demo_json("--scenario", SCENARIO)

    _assert_no_forbidden_content_keys(data)


def test_planner_adapter_trace_shows_symbolic_decisions_and_next_step():
    result = _run_demo("--scenario", SCENARIO, "--trace")

    assert result.returncode == 0, result.stderr
    assert "scenario: agent-loop-planner-friction" in result.stdout
    assert "planner selected symbolic step" in result.stdout
    assert "create_source_artifact" in result.stdout
    assert "submit_worker_handoff" in result.stdout
    assert "next development step" in result.stdout
    assert "raw artifact content" not in result.stdout.lower()
