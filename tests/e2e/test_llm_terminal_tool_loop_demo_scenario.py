import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
SCENARIO = "llm-terminal-tool-loop"

REQUIRED_TEXT_FIELDS = (
    "scenario: llm-terminal-tool-loop",
    "transport: in_process",
    "terminal_tool_loop_ok: true",
    "provider_tool_name: terminal_exec",
    "terminal_command: printf",
    "terminal_action_status: completed",
    "tool_result_message_ready: true",
    "tool_result_content_status: completed",
    "tool_result_artifact_ref_present: true",
    "final_answer_status: completed",
    "final_answer_artifact_ref_present: true",
    "provider_call_count: 2",
    "codex_call_count: 0",
    "real_llm_status: fake_provider",
    "network_listener_status: not_used",
    "memory_status: boundary_only",
)

REQUIRED_JSON_FIELDS = {
    "scenario",
    "run_status",
    "transport",
    "terminal_tool_loop_ok",
    "provider_name",
    "provider_model",
    "provider_tool_name",
    "provider_seen_tool_names",
    "provider_call_count",
    "terminal_command",
    "terminal_action_status",
    "terminal_output_verified",
    "tool_result_message_ready",
    "tool_result_content_status",
    "tool_result_artifact_ref",
    "tool_result_artifact_ref_present",
    "final_answer_status",
    "final_answer_artifact_ref_present",
    "codex_call_count",
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
    "assistant_message",
}

FORBIDDEN_OUTPUT_TEXT = (
    "TERMINAL_TOOL_LOOP_MESSAGE_SHOULD_NOT_LEAK",
    "TERMINAL_TOOL_LOOP_STDOUT_SHOULD_NOT_LEAK",
    "TERMINAL_TOOL_LOOP_FINAL_ANSWER_SHOULD_NOT_LEAK",
    "codex_task",
    "Codex",
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


def test_llm_terminal_tool_loop_demo_plain_cli_prints_terminal_only_summary():
    result = _run_demo("--scenario", SCENARIO)

    assert result.returncode == 0, result.stderr
    for field in REQUIRED_TEXT_FIELDS:
        assert field in result.stdout
    for forbidden in FORBIDDEN_OUTPUT_TEXT:
        assert forbidden not in result.stdout


def test_llm_terminal_tool_loop_demo_json_exposes_safe_terminal_status_only():
    data = _run_demo_json("--scenario", SCENARIO)

    assert REQUIRED_JSON_FIELDS.issubset(data)
    assert data["scenario"] == SCENARIO
    assert data["transport"] == "in_process"
    assert data["terminal_tool_loop_ok"] is True
    assert data["provider_tool_name"] == "terminal_exec"
    assert data["provider_seen_tool_names"] == ["terminal_exec"]
    assert data["provider_call_count"] == 2
    assert data["terminal_command"] == "printf"
    assert data["terminal_action_status"] == "completed"
    assert data["terminal_output_verified"] is True
    assert data["tool_result_message_ready"] is True
    assert data["tool_result_content_status"] == "completed"
    assert data["tool_result_artifact_ref"]["ref_type"] == "artifact"
    assert data["tool_result_artifact_ref_present"] is True
    assert data["final_answer_status"] == "completed"
    assert data["final_answer_artifact_ref_present"] is True
    assert data["codex_call_count"] == 0
    assert data["real_llm_status"] == "fake_provider"
    assert data["network_listener_status"] == "not_used"
    assert data["memory_status"] == "boundary_only"
    assert "approval.requested" not in data["event_types"]
    assert data["event_types"].count("action.started") == 2
    assert data["event_types"].count("run.completed") == 1
    _assert_no_forbidden_content_keys(data)
    rendered = json.dumps(data, sort_keys=True)
    for forbidden in FORBIDDEN_OUTPUT_TEXT:
        assert forbidden not in rendered


def test_llm_terminal_tool_loop_demo_trace_shows_terminal_path_without_codex():
    result = _run_demo("--scenario", SCENARIO, "--trace")

    assert result.returncode == 0, result.stderr
    assert "scenario: llm-terminal-tool-loop" in result.stdout
    assert "[1]" in result.stdout
    assert "provider sees terminal_exec only" in result.stdout
    assert "terminal_exec runs through submit_action" in result.stdout
    assert "safe tool-result message" in result.stdout
    assert "final answer artifact" in result.stdout
    assert "codex_call_count remains 0" in result.stdout
    for forbidden in FORBIDDEN_OUTPUT_TEXT:
        assert forbidden not in result.stdout


def test_llm_terminal_tool_loop_demo_trace_does_not_change_json_output_contract():
    plain_json = _run_demo("--scenario", SCENARIO, "--json")
    traced_json = _run_demo("--scenario", SCENARIO, "--trace", "--json")

    assert plain_json.returncode == 0, plain_json.stderr
    assert traced_json.returncode == 0, traced_json.stderr
    assert json.loads(traced_json.stdout) == json.loads(plain_json.stdout)
    assert "[1]" not in traced_json.stdout
