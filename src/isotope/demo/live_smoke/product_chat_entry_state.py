"""Product-chat entry state helpers for LLM live-smoke CLI commands."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ...features.chat.flow import (
    build_llm_product_chat_entry_resume_state,
    mark_llm_product_chat_entry_state_resumed,
    validate_llm_product_chat_entry_resume_state,
)
from ...platform.errors import IsotopeError


def _product_chat_entry_exit_code(payload: dict[str, Any]) -> int:
    if payload.get("status") == "failed" and isinstance(payload.get("error"), dict):
        return 2
    entry = payload.get("entry")
    if not isinstance(entry, dict):
        return 1
    if entry.get("status") in {"completed", "pending_user_approval"}:
        return 0
    if entry.get("status") == "bad_request":
        return 2
    preflight = payload.get("preflight")
    if isinstance(preflight, dict) and preflight.get("category") == "missing_configuration":
        return 2
    return 1


def _product_chat_entry_error_payload(
    exc: IsotopeError,
    *,
    command: str,
    runner_call_count: int = 0,
) -> dict[str, Any]:
    return {
        "command": command,
        "codex_runner": "fake",
        "status": "failed",
        "error": {
            "code": exc.code,
            "category": exc.category,
            "retryable": exc.retryable,
            "http_status": exc.http_status,
            "reason": _product_chat_entry_error_reason(exc),
            "summary": _product_chat_entry_error_summary(exc),
            "next_step": _product_chat_entry_error_next_step(exc),
        },
        "runner_call_count": runner_call_count,
    }


def _product_chat_entry_error_reason(exc: IsotopeError) -> str:
    details = exc.details if isinstance(exc.details, dict) else {}
    if isinstance(details.get("reason"), str):
        return details["reason"]
    if isinstance(details.get("resume_status"), str):
        return details["resume_status"]
    if isinstance(details.get("state"), str):
        return details["state"]
    if isinstance(details.get("field"), str):
        return details["field"]
    return exc.code


def _product_chat_entry_error_summary(exc: IsotopeError) -> str:
    if exc.code == "product_chat_entry_root_mismatch":
        return "The provided root does not match the local resume state."
    if exc.code == "product_chat_entry_state_already_resumed":
        return "The local resume state has already been used."
    if exc.code == "product_chat_entry_approval_unavailable":
        return "The saved approval is not available in this command root."
    if exc.code == "product_chat_entry_approval_already_resolved":
        return "The saved approval has already been resolved."
    if exc.code == "product_chat_entry_root_invalid":
        return "The command root is not a usable directory."
    if exc.code == "product_chat_entry_state_missing":
        return "The local resume state file was not found."
    if exc.code in {"product_chat_entry_state_invalid", "product_chat_entry_state_missing"}:
        return "The local resume state file is invalid."
    if exc.code == "product_chat_entry_state_save_failed":
        return "The local resume state could not be saved."
    if exc.code == "product_chat_entry_state_mark_failed":
        return "The resume completed, but the local state file could not be marked as used."
    return "The product-chat entry resume command could not continue."


def _product_chat_entry_error_next_step(exc: IsotopeError) -> str:
    if exc.code == "product_chat_entry_root_mismatch":
        return "omit --root or use the root recorded in the resume state"
    if exc.code == "product_chat_entry_state_already_resumed":
        return "start a new product-chat-entry request instead of reusing this state file"
    if exc.code == "product_chat_entry_approval_already_resolved":
        return "inspect the completed run, or create a fresh pending state"
    if exc.code == "product_chat_entry_approval_unavailable":
        return "use the original root/state file, or create a fresh pending state"
    if exc.code == "product_chat_entry_root_invalid":
        return "choose a command root that is a writable directory, then rerun product-chat-entry"
    if exc.code == "product_chat_entry_state_missing":
        return "check the --resume-state path, or create a fresh pending state with product-chat-entry --state-file"
    if exc.code == "product_chat_entry_state_save_failed":
        if _product_chat_entry_error_reason(exc) == "parent_not_directory":
            return "choose a --state-file path whose parent is a directory, then rerun product-chat-entry"
        return "choose a writable --state-file path and rerun product-chat-entry"
    if exc.code == "product_chat_entry_state_mark_failed":
        return "do not reuse this state file; inspect the completed run or create a fresh pending state"
    return "create a fresh pending state with product-chat-entry --state-file before resuming"


def _invalid_product_chat_entry_payload(message: Any) -> dict[str, Any] | None:
    if isinstance(message, str) and message.strip():
        return None
    preflight = {
        "ready": False,
        "gate": "blocked",
        "category": "invalid_request",
        "status": "bad_request",
        "reason_code": "llm_product_chat_user_message_required",
        "summary": "user message is required",
        "next_step": "pass a non-empty --message value",
    }
    return {
        "command": "llm_product_chat_app_entry",
        "codex_runner": "fake",
        "preflight": preflight,
        "entry": {
            "http_status": 400,
            "status": "bad_request",
            "error_code": "invalid_request",
            "reason_code": "llm_product_chat_user_message_required",
        },
        "runner_call_count": 0,
    }


def _invalid_product_chat_entry_mode_payload(args: Any) -> dict[str, Any] | None:
    if not getattr(args, "fake_entry_pending", False) or getattr(args, "fake_provider", False):
        return None
    reason_code = "llm_product_chat_fake_entry_pending_requires_fake_provider"
    preflight = {
        "ready": False,
        "gate": "blocked",
        "category": "invalid_request",
        "status": "bad_request",
        "reason_code": reason_code,
        "summary": "--fake-entry-pending only applies to the fake provider",
        "next_step": "pass --fake-provider with --fake-entry-pending, or remove --fake-entry-pending",
    }
    return {
        "command": "llm_product_chat_app_entry",
        "codex_runner": "fake",
        "preflight": preflight,
        "entry": {
            "http_status": 400,
            "status": "bad_request",
            "error_code": "invalid_request",
            "reason_code": reason_code,
        },
        "runner_call_count": 0,
    }


def _invalid_product_chat_entry_resume_mode_payload(args: Any) -> dict[str, Any] | None:
    if not (
        getattr(args, "message", None)
        or getattr(args, "state_file", None)
        or getattr(args, "fake_entry_pending", False)
    ):
        return None
    reason_code = "llm_product_chat_resume_state_conflicting_flags"
    preflight = {
        "ready": False,
        "gate": "blocked",
        "category": "invalid_request",
        "status": "bad_request",
        "reason_code": reason_code,
        "summary": "--resume-state cannot be combined with new-entry flags",
        "next_step": "use --resume-state by itself, or start a new product-chat-entry request",
    }
    return {
        "command": "llm_product_chat_app_entry_resume",
        "codex_runner": "fake",
        "preflight": preflight,
        "entry": {
            "http_status": 400,
            "status": "bad_request",
            "error_code": "invalid_request",
            "reason_code": reason_code,
        },
        "runner_call_count": 0,
    }


def _optional_path(value: Any) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    return Path(value)


def _prepare_product_chat_entry_root(root: Path) -> None:
    try:
        root.mkdir(parents=True, exist_ok=True)
    except FileExistsError as exc:
        raise _product_chat_entry_root_error("not_directory") from exc
    except PermissionError as exc:
        raise _product_chat_entry_root_error("unwritable") from exc
    if not root.is_dir():
        raise _product_chat_entry_root_error("not_directory")


def _product_chat_entry_root_error(reason: str) -> IsotopeError:
    return IsotopeError(
        "product-chat entry command root is invalid",
        code="product_chat_entry_root_invalid",
        category="validation",
        retryable=False,
        http_status=400,
        details={"reason": reason},
    )


def _entry_initial_complete_run(args: Any) -> bool:
    return _optional_path(getattr(args, "state_file", None)) is None


def _maybe_write_product_chat_entry_state(
    response: Any,
    *,
    root: Path,
    run_id: str,
    preflight: Mapping[str, Any],
    state_file: Path | None,
) -> dict[str, Any]:
    body = _response_dict(response)
    approval_id = body.get("approval_id")
    if state_file is None:
        if body.get("status") == "pending_user_approval" and isinstance(approval_id, str):
            return {
                "saved": False,
                "resume_ready": False,
                "next_step": "rerun product-chat-entry with --state-file to save a resumable pending state",
            }
        return {}
    if body.get("status") != "pending_user_approval" or not isinstance(approval_id, str):
        return {"saved": False, "resume_ready": False}
    try:
        state_file.parent.mkdir(parents=True, exist_ok=True)
    except FileExistsError as exc:
        raise _product_chat_entry_state_save_error("parent_not_directory") from exc
    except PermissionError as exc:
        raise _product_chat_entry_state_save_error("unwritable") from exc
    state = build_llm_product_chat_entry_resume_state(
        response,
        root=root,
        run_id=run_id,
        preflight=preflight,
    )
    if state is None:
        return {"saved": False, "resume_ready": False}
    try:
        state_file.write_text(json.dumps(state, sort_keys=True, indent=2), encoding="utf-8")
    except IsADirectoryError as exc:
        raise _product_chat_entry_state_save_error("not_file") from exc
    except PermissionError as exc:
        raise _product_chat_entry_state_save_error("unwritable") from exc
    return {
        "saved": True,
        "resume_ready": True,
        "next_step": "resume with product-chat-entry --resume-state using this saved state file",
    }


def _product_chat_entry_state_save_error(reason: str) -> IsotopeError:
    return IsotopeError(
        "product-chat entry state file could not be saved",
        code="product_chat_entry_state_save_failed",
        category="validation",
        retryable=False,
        http_status=400,
        details={"state": reason},
    )


def _product_chat_entry_state_mark_error(reason: str) -> IsotopeError:
    return IsotopeError(
        "product-chat entry state file could not be marked as resumed",
        code="product_chat_entry_state_mark_failed",
        category="validation",
        retryable=False,
        http_status=400,
        details={"state": reason},
    )


def _load_product_chat_entry_state(state_file: Path) -> dict[str, Any]:
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise IsotopeError(
            "product-chat entry state file not found",
            code="product_chat_entry_state_missing",
            category="not_found",
            retryable=False,
            http_status=404,
            details={"state": "missing"},
        ) from exc
    except json.JSONDecodeError as exc:
        raise IsotopeError(
            "product-chat entry state file is invalid",
            code="product_chat_entry_state_invalid",
            category="validation",
            retryable=False,
            http_status=400,
            details={"state": "invalid"},
        ) from exc
    except IsADirectoryError as exc:
        raise IsotopeError(
            "product-chat entry state file is invalid",
            code="product_chat_entry_state_invalid",
            category="validation",
            retryable=False,
            http_status=400,
            details={"state": "not_file"},
        ) from exc
    except PermissionError as exc:
        raise IsotopeError(
            "product-chat entry state file is invalid",
            code="product_chat_entry_state_invalid",
            category="validation",
            retryable=False,
            http_status=400,
            details={"state": "unreadable"},
        ) from exc
    if not isinstance(state, dict):
        raise IsotopeError(
            "product-chat entry state file is invalid",
            code="product_chat_entry_state_invalid",
            category="validation",
            retryable=False,
            http_status=400,
            details={"state": "invalid"},
        )
    return validate_llm_product_chat_entry_resume_state(state)


def _validate_product_chat_entry_resume_root(args: Any, state: Mapping[str, Any]) -> None:
    root_arg = getattr(args, "root", None)
    if not root_arg:
        return
    state_root = state.get("root")
    if not isinstance(state_root, str) or not state_root:
        return
    requested_root = Path(root_arg).expanduser().resolve(strict=False)
    saved_root = Path(state_root).expanduser().resolve(strict=False)
    if requested_root == saved_root:
        return
    raise IsotopeError(
        "product-chat entry resume root mismatch",
        code="product_chat_entry_root_mismatch",
        category="validation",
        retryable=False,
        http_status=400,
        details={"reason": "root_mismatch", "field": "root"},
    )


def _mark_product_chat_entry_state_resumed(
    state_file: Path,
    state: dict[str, Any],
    *,
    approval: Mapping[str, Any],
    entry: Mapping[str, Any],
) -> None:
    updated = mark_llm_product_chat_entry_state_resumed(state, approval=approval, entry=entry)
    try:
        state_file.write_text(json.dumps(updated, sort_keys=True, indent=2), encoding="utf-8")
    except PermissionError as exc:
        raise _product_chat_entry_state_mark_error("unwritable") from exc


def _preflight_from_result(result: Mapping[str, Any]) -> dict[str, Any]:
    diagnosis = result.get("diagnosis")
    if not isinstance(diagnosis, dict):
        diagnosis = {}
    return {
        "ready": False,
        "gate": "blocked",
        "category": _safe_body_string(diagnosis, "category") or "product_chat_smoke_failed",
        "status": _safe_body_string(result, "status"),
        "reason_code": _safe_body_string(result, "reason_code"),
        "summary": _safe_body_string(diagnosis, "summary"),
        "next_step": _safe_body_string(diagnosis, "next_step"),
    }


def _blocked_product_chat_entry_summary(preflight: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "http_status": 412,
        "status": "blocked_by_preflight",
        "reason_code": "llm_product_chat_preflight_blocked",
        "preflight_category": _safe_body_string(dict(preflight), "category"),
        "explanation": {
            "summary": _safe_body_string(dict(preflight), "summary")
            or "Product-chat preflight is not ready.",
            "next_step": _safe_body_string(dict(preflight), "next_step")
            or "Run product-chat diagnosis before submitting a chat turn.",
        },
    }


def _response_dict(response: Any) -> dict[str, Any]:
    body = response.json() if callable(getattr(response, "json", None)) else getattr(response, "body", None)
    return body if isinstance(body, dict) else {}


def _run_state_status(body: dict[str, Any]) -> Any:
    run_state = body.get("run_state")
    if isinstance(run_state, dict) and isinstance(run_state.get("status"), str):
        return run_state["status"]
    return body.get("status")


def _safe_body_string(body: Mapping[str, Any], key: str) -> str | None:
    value = body.get(key)
    if isinstance(value, str) and value:
        return value[:128]
    return None


__all__ = [
    "_blocked_product_chat_entry_summary",
    "_entry_initial_complete_run",
    "_invalid_product_chat_entry_mode_payload",
    "_invalid_product_chat_entry_payload",
    "_invalid_product_chat_entry_resume_mode_payload",
    "_load_product_chat_entry_state",
    "_mark_product_chat_entry_state_resumed",
    "_maybe_write_product_chat_entry_state",
    "_optional_path",
    "_preflight_from_result",
    "_prepare_product_chat_entry_root",
    "_product_chat_entry_error_payload",
    "_product_chat_entry_exit_code",
    "_response_dict",
    "_run_state_status",
    "_validate_product_chat_entry_resume_root",
]
