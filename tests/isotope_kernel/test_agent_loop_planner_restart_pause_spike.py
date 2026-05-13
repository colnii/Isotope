import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
SCENARIO = "agent-loop-planner-restart-pause"

REQUIRED_TEXT_FIELDS = (
    "scenario: agent-loop-planner-restart-pause",
    "planner_restart_pause_ok: true",
    "approval_pending_before_restart: true",
    "restart_resume_ok: true",
    "kernel_friction_count: 0",
    "private_append_required: false",
    "model_status: not_used",
    "scheduler_status: not_used",
)

REQUIRED_JSON_FIELDS = {
    "scenario",
    "run_status",
    "transport",
    "planner_restart_pause_ok",
    "planner_adapter_status",
    "planner_decisions_before_restart",
    "planner_decisions_after_restart",
    "approval_pending_before_restart",
    "restart_resume_ok",
    "kernel_friction",
    "kernel_friction_count",
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
    "model_prompt",
    "model_response",
    "raw_artifact_content",
    "raw_content",
}


def _run_demo(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "isotope_kernel.demo", *args],
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


def test_planner_restart_pause_plain_cli_prints_restart_summary():
    result = _run_demo("--scenario", SCENARIO)

    assert result.returncode == 0, result.stderr
    for field in REQUIRED_TEXT_FIELDS:
        assert field in result.stdout
    assert "real llm" not in result.stdout.lower()


def test_planner_restart_pause_json_reports_resume_after_restart():
    data = _run_demo_json("--scenario", SCENARIO)

    assert REQUIRED_JSON_FIELDS.issubset(data)
    assert data["scenario"] == SCENARIO
    assert data["planner_restart_pause_ok"] is True
    assert data["planner_adapter_status"] == "deterministic_fixture"
    assert data["approval_pending_before_restart"] is True
    assert data["restart_resume_ok"] is True
    assert data["private_append_required"] is False
    assert data["kernel_friction"] == []
    assert data["kernel_friction_count"] == 0
    assert data["replay_ok"] is True
    assert data["checkpoint_ok"] is True
    assert data["run_status"] == "completed"
    assert data["planner_decisions_before_restart"] == [
        "create_source_artifact",
        "submit_worker_handoff",
        "submit_approval_gated_action",
    ]
    assert data["planner_decisions_after_restart"] == [
        "get_pending_approvals",
        "resolve_approval",
        "verify_replay_checkpoint",
    ]


def test_planner_restart_pause_keeps_deferred_integrations_disabled():
    data = _run_demo_json("--scenario", SCENARIO)

    assert data["transport"] == "in_process"
    assert data["model_status"] == "not_used"
    assert data["scheduler_status"] == "not_used"
    assert data["provider_status"] == "not_used"
    assert data.get("network_listener_status", "not_used") == "not_used"
    assert data.get("memory_query_status", "not_enabled") == "not_enabled"


def test_planner_restart_pause_json_excludes_model_and_artifact_full_content():
    data = _run_demo_json("--scenario", SCENARIO)

    _assert_no_forbidden_content_keys(data)


def test_planner_restart_pause_trace_shows_pause_restart_and_resume():
    result = _run_demo("--scenario", SCENARIO, "--trace")

    assert result.returncode == 0, result.stderr
    assert "scenario: agent-loop-planner-restart-pause" in result.stdout
    assert "pause at approval" in result.stdout
    assert "restart server" in result.stdout
    assert "resume approval" in result.stdout
    assert "next development step" in result.stdout
    assert "raw artifact content" not in result.stdout.lower()
