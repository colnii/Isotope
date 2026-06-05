import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
SCENARIO = "llm-tool-result-loop"

REQUIRED_TEXT_FIELDS = (
    "scenario: llm-tool-result-loop",
    "transport: in_process",
    "tool_result_loop_ok: true",
    "provider_name: deepseek",
    "provider_model: deepseek-v4-flash",
    "provider_tool_name: codex_task",
    "route_result_status: pending_user_approval",
    "approval_ok: true",
    "codex_started_after_approval: true",
    "codex_call_count: 2",
    "tool_result_message_ready: true",
    "tool_result_message_role: tool",
    "tool_result_message_tool_call_id: call_demo_provider_route",
    "tool_result_content_status: completed",
    "tool_result_artifact_ref_present: true",
    "followup_provider_call_count: 2",
    "followup_result_status: pending_user_approval",
    "followup_provider_tool_call_id: call_demo_followup_route",
    "followup_tool_name: codex_task",
    "followup_submission_status: pending_user_approval",
    "followup_action_submitted: true",
    "first_run_status_after_approval: running",
    "second_approval_ok: true",
    "second_codex_started_after_approval: true",
    "tool_result_loop_status: two_tool_actions_completed",
    "multi_tool_loop_status: two_step_demo_only",
    "real_llm_status: deterministic_test_provider",
    "network_listener_status: not_used",
    "memory_status: active",
)

REQUIRED_JSON_FIELDS = {
    "scenario",
    "run_status",
    "transport",
    "tool_result_loop_ok",
    "provider_name",
    "provider_model",
    "provider_tool_name",
    "route_result_status",
    "approval_ok",
    "codex_started_after_approval",
    "codex_call_count",
    "tool_result_message_ready",
    "tool_result_message_role",
    "tool_result_message_tool_call_id",
    "tool_result_content_status",
    "tool_result_artifact_ref",
    "tool_result_artifact_ref_present",
    "followup_provider_call_count",
    "followup_result_status",
    "followup_provider_tool_call_id",
    "followup_tool_name",
    "followup_submission_status",
    "followup_action_submitted",
    "first_run_status_after_approval",
    "second_approval_ok",
    "second_codex_started_after_approval",
    "tool_result_loop_status",
    "multi_tool_loop_status",
    "event_count",
    "event_types",
    "replay_ok",
    "checkpoint_ok",
    "real_llm_status",
    "network_listener_status",
    "memory_status",
}

FORBIDDEN_CONTENT_KEYS = {
    "content",
    "artifact_content",
    "full_content",
    "full_text",
    "raw_content",
    "raw_artifact_content",
    "prompt",
    "messages",
    "stdout",
    "stderr",
    "stdin",
}

FORBIDDEN_OUTPUT_TEXT = (
    "LLM_TOOL_RESULT_DEMO_MESSAGE_SHOULD_NOT_LEAK",
    "LLM_PROVIDER_DEMO_PROMPT_SHOULD_NOT_LEAK",
    "LLM_TOOL_RESULT_FOLLOWUP_PROMPT_SHOULD_NOT_LEAK",
    "LLM_TOOL_RESULT_DEMO_OUTPUT_SHOULD_NOT_LEAK",
    '"content"',
    "'content'",
)


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


def test_llm_tool_result_loop_demo_plain_cli_prints_short_boundary_summary():
    result = _run_demo("--scenario", SCENARIO)

    assert result.returncode == 0, result.stderr
    for field in REQUIRED_TEXT_FIELDS:
        assert field in result.stdout
    for forbidden in FORBIDDEN_OUTPUT_TEXT:
        assert forbidden not in result.stdout


def test_llm_tool_result_loop_demo_json_exposes_safe_tool_result_status_only():
    data = _run_demo_json("--scenario", SCENARIO)

    assert REQUIRED_JSON_FIELDS.issubset(data)
    assert data["scenario"] == SCENARIO
    assert data["transport"] == "in_process"
    assert data["tool_result_loop_ok"] is True
    assert data["provider_name"] == "deepseek"
    assert data["provider_model"] == "deepseek-v4-flash"
    assert data["provider_tool_name"] == "codex_task"
    assert data["route_result_status"] == "pending_user_approval"
    assert data["approval_ok"] is True
    assert data["codex_started_after_approval"] is True
    assert data["codex_call_count"] == 2
    assert data["tool_result_message_ready"] is True
    assert data["tool_result_message_role"] == "tool"
    assert data["tool_result_message_tool_call_id"] == "call_demo_provider_route"
    assert data["tool_result_content_status"] == "completed"
    assert data["tool_result_artifact_ref"]["ref_type"] == "artifact"
    assert data["tool_result_artifact_ref_present"] is True
    assert data["followup_provider_call_count"] == 2
    assert data["followup_result_status"] == "pending_user_approval"
    assert data["followup_provider_tool_call_id"] == "call_demo_followup_route"
    assert data["followup_tool_name"] == "codex_task"
    assert data["followup_submission_status"] == "pending_user_approval"
    assert data["followup_action_submitted"] is True
    assert data["first_run_status_after_approval"] == "running"
    assert data["second_approval_ok"] is True
    assert data["second_codex_started_after_approval"] is True
    assert data["tool_result_loop_status"] == "two_tool_actions_completed"
    assert data["multi_tool_loop_status"] == "two_step_demo_only"
    assert data["real_llm_status"] == "deterministic_test_provider"
    assert data["network_listener_status"] == "not_used"
    assert data["memory_status"] == "active"
    assert "approval.resolved" in data["event_types"]
    assert "action.started" in data["event_types"]
    assert "artifact.created" in data["event_types"]
    assert data["event_types"].count("approval.requested") == 2
    assert data["event_types"].count("action.started") == 2
    assert data["event_types"].count("run.completed") == 1
    _assert_no_forbidden_content_keys(data)
    rendered = json.dumps(data, sort_keys=True)
    for forbidden in FORBIDDEN_OUTPUT_TEXT:
        assert forbidden not in rendered


def test_llm_tool_result_loop_demo_trace_shows_safe_message_preparation_without_raw_content():
    result = _run_demo("--scenario", SCENARIO, "--trace")

    assert result.returncode == 0, result.stderr
    assert "scenario: llm-tool-result-loop" in result.stdout
    assert "[1]" in result.stdout
    assert "provider route" in result.stdout
    assert "approval resolved" in result.stdout
    assert "Codex CLI backend called after approval" in result.stdout
    assert "tool result message prepared" in result.stdout
    assert "follow-up model choice submitted for approval" in result.stdout
    assert "first approval left run open" in result.stdout
    assert "second approval completed run" in result.stdout
    assert "artifact ref only" in result.stdout
    assert "no transcript" in result.stdout
    for forbidden in FORBIDDEN_OUTPUT_TEXT:
        assert forbidden not in result.stdout


def test_llm_tool_result_loop_demo_trace_does_not_change_json_output_contract():
    plain_json = _run_demo("--scenario", SCENARIO, "--json")
    traced_json = _run_demo("--scenario", SCENARIO, "--trace", "--json")

    assert plain_json.returncode == 0, plain_json.stderr
    assert traced_json.returncode == 0, traced_json.stderr
    assert json.loads(traced_json.stdout) == json.loads(plain_json.stdout)
    assert "[1]" not in traced_json.stdout
