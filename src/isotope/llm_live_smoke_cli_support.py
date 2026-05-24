"""CLI formatting and local-state helpers for LLM live-smoke commands."""

from __future__ import annotations

from typing import Any

from .llm_live_smoke_product_chat_entry_state import (
    _blocked_product_chat_entry_summary,
    _entry_initial_complete_run,
    _invalid_product_chat_entry_mode_payload,
    _invalid_product_chat_entry_payload,
    _invalid_product_chat_entry_resume_mode_payload,
    _load_product_chat_entry_state,
    _mark_product_chat_entry_state_resumed,
    _maybe_write_product_chat_entry_state,
    _optional_path,
    _preflight_from_result,
    _prepare_product_chat_entry_root,
    _product_chat_entry_error_payload,
    _product_chat_entry_exit_code,
    _response_dict,
    _run_state_status,
    _safe_body_string,
    _validate_product_chat_entry_resume_root,
)


def _print_terminal_tool_smoke_plain(payload: dict[str, Any]) -> None:
    result = payload.get("result")
    if not isinstance(result, dict):
        result = {}
    print(f"command: {payload.get('command')}")
    print(f"status: {result.get('status')}")
    print(f"reason_code: {result.get('reason_code')}")
    print(f"provider: {result.get('provider')}")
    if result.get("model"):
        print(f"model: {result.get('model')}")
    print(f"tool_name: {result.get('tool_name')}")
    print(f"tool_result_status: {result.get('tool_result_status')}")
    print(f"artifact_ref_present: {str(result.get('artifact_ref_present')).lower()}")
    print(f"provider_call_count: {payload.get('provider_call_count')}")
    print(f"codex_call_count: {payload.get('codex_call_count')}")
    diagnosis = result.get("diagnosis")
    if isinstance(diagnosis, dict):
        print(f"diagnosis: {diagnosis.get('category')}")
        print(f"diagnosis_summary: {diagnosis.get('summary')}")
        print(f"diagnosis_next_step: {diagnosis.get('next_step')}")
    preflight = result.get("preflight")
    if isinstance(preflight, dict):
        print(f"preflight_ready: {str(preflight.get('ready')).lower()}")
        print(f"preflight_gate: {preflight.get('gate')}")


def _print_product_chat_smoke_plain(payload: dict[str, Any]) -> None:
    result = payload.get("result")
    if not isinstance(result, dict):
        result = {}
    print(f"command: {payload.get('command')}")
    print(f"status: {result.get('status')}")
    print(f"reason_code: {result.get('reason_code')}")
    print(f"provider: {result.get('provider')}")
    if result.get("model"):
        print(f"model: {result.get('model')}")
    print(f"codex_runner: {payload.get('codex_runner')}")
    print(f"runner_call_count: {payload.get('runner_call_count')}")
    print(f"case_count: {result.get('case_count')}")
    cases = result.get("cases")
    if isinstance(cases, list) and cases:
        print("cases:")
        for case in cases:
            if not isinstance(case, dict):
                continue
            print(
                "- "
                f"{case.get('case')}: "
                f"{case.get('status')} "
                f"(http_status={case.get('http_status')}, run_state={case.get('run_state_status')})"
            )
    diagnosis = result.get("diagnosis")
    if isinstance(diagnosis, dict):
        print(f"diagnosis: {diagnosis.get('category')}")
        print(f"diagnosis_summary: {diagnosis.get('summary')}")
        print(f"diagnosis_next_step: {diagnosis.get('next_step')}")
    preflight = result.get("preflight")
    if isinstance(preflight, dict):
        print(f"preflight_ready: {str(preflight.get('ready')).lower()}")
        print(f"preflight_gate: {preflight.get('gate')}")


def _print_product_chat_entry_plain(payload: dict[str, Any]) -> None:
    preflight = payload.get("preflight")
    if not isinstance(preflight, dict):
        preflight = {}
    entry = payload.get("entry")
    if not isinstance(entry, dict):
        entry = {}
    print(f"command: {payload.get('command')}")
    print(f"preflight_ready: {str(preflight.get('ready')).lower()}")
    print(f"preflight_gate: {preflight.get('gate')}")
    print(f"preflight_category: {preflight.get('category')}")
    print(f"entry_status: {entry.get('status')}")
    print(f"entry_http_status: {entry.get('http_status')}")
    if entry.get("provider_status"):
        print(f"entry_provider_status: {entry.get('provider_status')}")
    if "requires_approval" in entry:
        print(f"entry_requires_approval: {str(entry.get('requires_approval')).lower()}")
    if "approval_id_present" in entry:
        print(f"approval_id_present: {str(entry.get('approval_id_present')).lower()}")
    if "assistant_message_present" in entry:
        print(f"assistant_message_present: {str(entry.get('assistant_message_present')).lower()}")
    if "artifact_ref_present" in entry:
        print(f"artifact_ref_present: {str(entry.get('artifact_ref_present')).lower()}")
    if isinstance(entry.get("next_step"), str):
        print(f"entry_next_step: {entry.get('next_step')}")
    explanation = entry.get("explanation")
    if isinstance(explanation, dict):
        print(f"entry_summary: {explanation.get('summary')}")
        print(f"entry_next_step: {explanation.get('next_step')}")
    pending_state = payload.get("pending_state")
    if isinstance(pending_state, dict):
        print(f"pending_state_saved: {str(pending_state.get('saved')).lower()}")
        print(f"pending_state_resume_ready: {str(pending_state.get('resume_ready')).lower()}")
        if isinstance(pending_state.get("next_step"), str):
            print(f"pending_state_next_step: {pending_state.get('next_step')}")
    print(f"codex_runner: {payload.get('codex_runner')}")
    print(f"runner_call_count: {payload.get('runner_call_count')}")


def _print_product_chat_entry_resume_plain(payload: dict[str, Any]) -> None:
    error = payload.get("error")
    if isinstance(error, dict):
        print(f"command: {payload.get('command')}")
        print(f"status: {payload.get('status')}")
        print(f"error_code: {error.get('code')}")
        print(f"error_reason: {error.get('reason')}")
        print(f"error_summary: {error.get('summary')}")
        print(f"error_next_step: {error.get('next_step')}")
        print(f"codex_runner: {payload.get('codex_runner')}")
        print(f"runner_call_count: {payload.get('runner_call_count')}")
        return
    approval = payload.get("approval")
    if not isinstance(approval, dict):
        approval = {}
    entry = payload.get("entry")
    if not isinstance(entry, dict):
        entry = {}
    print(f"command: {payload.get('command')}")
    print(f"approval_status: {approval.get('status')}")
    print(f"approval_tool_execution_status: {approval.get('tool_execution_status')}")
    print(f"approval_artifact_ref_present: {str(approval.get('artifact_ref_present')).lower()}")
    print(f"entry_status: {entry.get('status')}")
    print(f"entry_http_status: {entry.get('http_status')}")
    if entry.get("provider_status"):
        print(f"entry_provider_status: {entry.get('provider_status')}")
    if "assistant_message_present" in entry:
        print(f"assistant_message_present: {str(entry.get('assistant_message_present')).lower()}")
    if "artifact_ref_present" in entry:
        print(f"artifact_ref_present: {str(entry.get('artifact_ref_present')).lower()}")
    if "tool_result_artifact_ref_present" in entry:
        print(
            "tool_result_artifact_ref_present: "
            f"{str(entry.get('tool_result_artifact_ref_present')).lower()}"
        )
    print(f"codex_runner: {payload.get('codex_runner')}")
    print(f"runner_call_count: {payload.get('runner_call_count')}")


def _product_chat_smoke_exit_code(result: dict[str, Any]) -> int:
    if result.get("status") in {"completed", "skipped"}:
        return 0
    if result.get("status") == "missing_configuration":
        return 2
    return 1


def _terminal_tool_smoke_exit_code(result: dict[str, Any]) -> int:
    if result.get("status") == "completed" and result.get("tool_result_status") == "completed":
        return 0
    if result.get("status") == "skipped":
        return 0
    if result.get("status") == "missing_configuration":
        return 2
    if result.get("reason_code") in {
        "llm_provider_selected_unoffered_tool",
        "invalid_model_tool_call",
    }:
        return 2
    return 1
