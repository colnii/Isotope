import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
SCENARIO = "llm-product-chat-app-entry"

REQUIRED_TEXT_FIELDS = (
    "scenario: llm-product-chat-app-entry",
    "transport: in_process",
    "app_entry_readiness_check_ok: true",
    "user_message_entry_ok: true",
    "blocked_status_code: 412",
    "blocked_result_status: blocked_by_readiness_check",
    "blocked_no_side_effects: true",
    "ready_readiness_check_ready: true",
    "ready_status_code: 200",
    "ready_result_status: completed",
    "ready_forwarded_to_route: true",
    "provider_call_count: 1",
    "codex_call_count: 0",
    "real_llm_status: fake_provider",
    "network_listener_status: not_used",
    "memory_status: active",
)

REQUIRED_JSON_FIELDS = {
    "scenario",
    "run_status",
    "transport",
    "app_entry_readiness_check_ok",
    "user_message_entry_ok",
    "blocked_status_code",
    "blocked_result_status",
    "blocked_no_side_effects",
    "ready_readiness_check_ready",
    "ready_status_code",
    "ready_result_status",
    "ready_forwarded_to_route",
    "assistant_message_present",
    "artifact_ref_present",
    "provider_call_count",
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
    "APP_ENTRY_DEMO_BLOCKED_MESSAGE_SHOULD_NOT_LEAK",
    "APP_ENTRY_DEMO_READY_MESSAGE_SHOULD_NOT_LEAK",
    "APP_ENTRY_DEMO_FINAL_ANSWER_SHOULD_NOT_LEAK",
    "APP_ENTRY_DEMO_STDOUT_SHOULD_NOT_LEAK",
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


def test_llm_product_chat_app_entry_demo_plain_cli_prints_gate_summary_only():
    result = _run_demo("--scenario", SCENARIO)

    assert result.returncode == 0, result.stderr
    for field in REQUIRED_TEXT_FIELDS:
        assert field in result.stdout
    for forbidden in FORBIDDEN_OUTPUT_TEXT:
        assert forbidden not in result.stdout


def test_llm_product_chat_app_entry_demo_json_exposes_safe_gate_status_only():
    data = _run_demo_json("--scenario", SCENARIO)

    assert REQUIRED_JSON_FIELDS.issubset(data)
    assert data["scenario"] == SCENARIO
    assert data["transport"] == "in_process"
    assert data["app_entry_readiness_check_ok"] is True
    assert data["user_message_entry_ok"] is True
    assert data["blocked_status_code"] == 412
    assert data["blocked_result_status"] == "blocked_by_readiness_check"
    assert data["blocked_no_side_effects"] is True
    assert data["ready_readiness_check_ready"] is True
    assert data["ready_status_code"] == 200
    assert data["ready_result_status"] == "completed"
    assert data["ready_forwarded_to_route"] is True
    assert data["assistant_message_present"] is True
    assert data["artifact_ref_present"] is True
    assert data["provider_call_count"] == 1
    assert data["codex_call_count"] == 0
    assert data["real_llm_status"] == "fake_provider"
    assert data["network_listener_status"] == "not_used"
    assert data["memory_status"] == "active"
    assert "run.completed" in data["event_types"]
    assert "artifact.created" in data["event_types"]
    _assert_no_forbidden_content_keys(data)
    rendered = json.dumps(data, sort_keys=True)
    for forbidden in FORBIDDEN_OUTPUT_TEXT:
        assert forbidden not in rendered


def test_llm_product_chat_app_entry_demo_trace_shows_block_then_ready_without_content():
    result = _run_demo("--scenario", SCENARIO, "--trace")

    assert result.returncode == 0, result.stderr
    assert "scenario: llm-product-chat-app-entry" in result.stdout
    assert "[1]" in result.stdout
    assert "readiness_check blocked" in result.stdout
    assert "no provider call" in result.stdout
    assert "readiness_check ready" in result.stdout
    assert "user message accepted" in result.stdout
    assert "forwarded to product-chat route" in result.stdout
    assert "final answer artifact" in result.stdout
    assert "no real network" in result.stdout
    for forbidden in FORBIDDEN_OUTPUT_TEXT:
        assert forbidden not in result.stdout


def test_llm_product_chat_app_entry_demo_trace_does_not_change_json_output_contract():
    plain_json = _run_demo("--scenario", SCENARIO, "--json")
    traced_json = _run_demo("--scenario", SCENARIO, "--trace", "--json")

    assert plain_json.returncode == 0, plain_json.stderr
    assert traced_json.returncode == 0, traced_json.stderr
    assert json.loads(traced_json.stdout) == json.loads(plain_json.stdout)
    assert "[1]" not in traced_json.stdout
