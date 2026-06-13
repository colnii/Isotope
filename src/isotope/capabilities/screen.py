"""Screen-specific deterministic capability runners."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ..execution.screen.backend_types import (
    ScreenAction,
    SUPPORTED_EXECUTION_MODES,
)
from ..execution.screen.windows_backend import WindowsScreenBackend
from ..features.screen.artifacts import report_screen_artifacts
from ..runtime.in_process import InProcessServer
from ..platform.schemas.input_contract import missing_required_input_keys


SCREEN_CONTROL_CAPABILITY = "screen.control"
SCREEN_OBSERVE_CAPABILITY = "screen.observe"
SCREEN_REPORT_CAPABILITY = "screen.report"
SCREEN_CAPABILITIES = {
    SCREEN_CONTROL_CAPABILITY,
    SCREEN_OBSERVE_CAPABILITY,
    SCREEN_REPORT_CAPABILITY,
}


def is_screen_projection_capability(capability_id: str) -> bool:
    return capability_id == SCREEN_REPORT_CAPABILITY


def is_screen_capability(capability_id: str) -> bool:
    return capability_id in SCREEN_CAPABILITIES


def validate_screen_inputs(
    *,
    capability_id: str,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    if capability_id == SCREEN_CONTROL_CAPABILITY:
        return _validate_screen_control_inputs(
            inputs=inputs,
            missing_inputs=missing_inputs,
        )
    if capability_id == SCREEN_OBSERVE_CAPABILITY:
        return _validate_screen_observe_inputs(
            inputs=inputs,
            missing_inputs=missing_inputs,
        )
    if capability_id == SCREEN_REPORT_CAPABILITY:
        return _validate_screen_report_inputs(
            inputs=inputs,
            missing_inputs=missing_inputs,
        )
    return dict(inputs or {})


def validate_screen_projection_inputs(
    *,
    capability_id: str,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    if capability_id != SCREEN_REPORT_CAPABILITY:
        return dict(inputs or {})
    return _validate_screen_report_inputs(
        inputs=inputs,
        missing_inputs=missing_inputs,
    )


def run_screen_observe(
    *,
    root_path: Path | str | None = None,
    inputs: Mapping[str, Any] | None,
) -> dict[str, Any]:
    required_inputs = ["target_selector"]
    missing_inputs = _missing_inputs(required_inputs, inputs)
    if missing_inputs:
        raise ValueError("missing required capability inputs: " + ", ".join(missing_inputs))
    input_mapping = _validate_screen_observe_inputs(
        inputs=inputs,
        missing_inputs=missing_inputs,
    )
    root = _screen_observe_root(input_mapping, root_path=root_path)
    api = InProcessServer(
        root,
        screen_backend=WindowsScreenBackend(),
        screen_backend_config={
            "backend_id": "windows_screen",
            "backend_version": "0.1",
        },
    )
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="screen observe capacity")
    run_id = run["run_id"]
    observe_result = api.submit_action(
        run_id,
        _screen_observe_intent(input_mapping),
    )
    payload = report_screen_artifacts(root, run_id=run_id)
    observe_summary = {
        "status": observe_result["status"],
        "run_id": run_id,
        "execution_id": observe_result.get("execution_id"),
        "artifact_ref": _ref_to_dict(observe_result.get("artifact_ref")),
    }
    failure = _screen_observe_failure(api, run_id=run_id)
    if failure is not None:
        observe_summary["failure"] = failure
    return {
        "kind": "capability_run_result",
        "capability_id": SCREEN_OBSERVE_CAPABILITY,
        "status": "completed",
        "runner_kind": "deterministic_local",
        "screen_observe": observe_summary,
        "screen_report": payload,
    }


def run_screen_control(
    *,
    root_path: Path | str | None = None,
    inputs: Mapping[str, Any] | None,
) -> dict[str, Any]:
    required_inputs = ["target_selector", "execution_mode", "actions"]
    missing_inputs = _missing_inputs(required_inputs, inputs)
    if missing_inputs:
        raise ValueError("missing required capability inputs: " + ", ".join(missing_inputs))
    input_mapping = _validate_screen_control_inputs(
        inputs=inputs,
        missing_inputs=missing_inputs,
    )
    root = _screen_root(input_mapping, root_path=root_path)
    api = InProcessServer(
        root,
        screen_backend=WindowsScreenBackend(),
        screen_backend_config={
            "backend_id": "windows_screen",
            "backend_version": "0.1",
        },
    )
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="screen control capacity")
    run_id = run["run_id"]
    execution_mode = input_mapping["execution_mode"]
    control_result = api.submit_action(
        run_id,
        _screen_control_intent(input_mapping),
        requires_approval=execution_mode == "execute",
    )
    payload = report_screen_artifacts(root, run_id=run_id)
    control_summary = {
        "status": control_result["status"],
        "run_id": run_id,
        "execution_id": control_result.get("execution_id"),
        "approval_id": control_result.get("approval_id"),
        "artifact_ref": _ref_to_dict(control_result.get("artifact_ref")),
    }
    failure = _screen_action_failure(api, run_id=run_id)
    if failure is not None:
        control_summary["failure"] = failure
    status = "pending_user_approval" if control_result["status"] == "pending_user_approval" else "completed"
    return {
        "kind": "capability_run_result",
        "capability_id": SCREEN_CONTROL_CAPABILITY,
        "status": status,
        "runner_kind": "deterministic_local",
        "screen_control": control_summary,
        "screen_report": payload,
    }


def run_screen_report(*, inputs: Mapping[str, Any] | None) -> dict[str, Any]:
    required_inputs = ["root", "run_id"]
    missing_inputs = _missing_inputs(required_inputs, inputs)
    if missing_inputs:
        raise ValueError("missing required capability inputs: " + ", ".join(missing_inputs))
    input_mapping = _validate_screen_report_inputs(
        inputs=inputs,
        missing_inputs=missing_inputs,
    )
    payload = report_screen_artifacts(
        Path(input_mapping["root"]).expanduser(),
        run_id=input_mapping["run_id"],
    )
    return {
        "kind": "capability_run_result",
        "capability_id": SCREEN_REPORT_CAPABILITY,
        "status": "completed",
        "runner_kind": "deterministic_projection",
        "screen_report": payload,
    }


def _missing_inputs(
    required_inputs: list[str], inputs: Mapping[str, Any] | None
) -> list[str]:
    return missing_required_input_keys(inputs, required_inputs)


def _validate_screen_report_inputs(
    *,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    input_mapping = inputs or {}
    for name in ("root", "run_id"):
        if name in missing_inputs:
            continue
        value = input_mapping.get(name)
        if not isinstance(value, str):
            raise ValueError(f"{name} must be a string")
        if not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
    return dict(input_mapping)


def _validate_screen_observe_inputs(
    *,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    input_mapping = inputs or {}
    if "target_selector" not in missing_inputs:
        _validate_target_selector(input_mapping.get("target_selector"))
    if "root" in input_mapping:
        value = input_mapping.get("root")
        if not isinstance(value, str):
            raise ValueError("root must be a string")
        if not value.strip():
            raise ValueError("root must be a non-empty string")
    if "mode" in input_mapping:
        value = input_mapping.get("mode")
        if not isinstance(value, str) or value not in {"non_intrusive"}:
            raise ValueError("mode must be non_intrusive")
    if "capture" in input_mapping:
        _validate_capture(input_mapping.get("capture"))
    if "target_allowlist" in input_mapping:
        _validate_target_allowlist(input_mapping.get("target_allowlist"))
    return dict(input_mapping)


def _validate_screen_control_inputs(
    *,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    input_mapping = inputs or {}
    if "target_selector" not in missing_inputs:
        _validate_target_selector(input_mapping.get("target_selector"))
    if "root" in input_mapping:
        value = input_mapping.get("root")
        if not isinstance(value, str):
            raise ValueError("root must be a string")
        if not value.strip():
            raise ValueError("root must be a non-empty string")
    if "execution_mode" not in missing_inputs:
        value = input_mapping.get("execution_mode")
        if not isinstance(value, str) or value not in SUPPORTED_EXECUTION_MODES:
            raise ValueError("execution_mode must be dry_run or execute")
    if "actions" not in missing_inputs:
        _validate_actions(input_mapping.get("actions"))
    if "target_allowlist" in input_mapping:
        _validate_target_allowlist(input_mapping.get("target_allowlist"))
    return dict(input_mapping)


def _validate_target_selector(value: Any) -> None:
    if not isinstance(value, dict):
        raise ValueError("target_selector must be an object")
    kind = value.get("kind")
    if not isinstance(kind, str) or not kind:
        raise ValueError("target_selector.kind must be a non-empty string")
    selector = value.get("selector")
    if not isinstance(selector, dict) or not selector:
        raise ValueError("target_selector.selector must be a non-empty object")


def _validate_capture(value: Any) -> None:
    if not isinstance(value, list) or not value:
        raise ValueError("capture must be a non-empty list")
    for index, item in enumerate(value):
        if item not in {"metadata", "screenshot"}:
            raise ValueError(f"capture[{index}] must be metadata or screenshot")


def _validate_actions(value: Any) -> None:
    if not isinstance(value, list) or not value:
        raise ValueError("actions must be a non-empty list")
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(f"actions[{index}] must be an object")
        try:
            ScreenAction.from_dict(item)
        except ValueError as exc:
            raise ValueError(f"actions[{index}] is not supported") from exc


def _validate_target_allowlist(value: Any) -> None:
    if not isinstance(value, dict):
        raise ValueError("target_allowlist must be an object")
    for field_name in ("allowed_apps", "allowed_title_contains"):
        items = value.get(field_name, [])
        if not isinstance(items, list) or not all(isinstance(item, str) for item in items):
            raise ValueError(f"target_allowlist.{field_name} must be a list of strings")
    allow_first_match_execute = value.get("allow_first_match_execute")
    if allow_first_match_execute is not None and not isinstance(allow_first_match_execute, bool):
        raise ValueError("target_allowlist.allow_first_match_execute must be a boolean")


def _screen_root(
    input_mapping: Mapping[str, Any],
    *,
    root_path: Path | str | None,
) -> Path:
    root = input_mapping.get("root")
    if isinstance(root, str) and root.strip():
        return Path(root).expanduser()
    if root_path is None:
        raise ValueError("root or root_path is required")
    return Path(root_path).expanduser()


def _screen_observe_root(
    input_mapping: Mapping[str, Any],
    *,
    root_path: Path | str | None,
) -> Path:
    return _screen_root(input_mapping, root_path=root_path)


def _screen_observe_intent(input_mapping: Mapping[str, Any]) -> dict[str, Any]:
    intent = {
        "action": "call_tool",
        "tool": "screen_observe",
        "target_selector": dict(input_mapping["target_selector"]),
        "mode": input_mapping.get("mode", "non_intrusive"),
        "capture": list(input_mapping.get("capture", ["metadata", "screenshot"])),
        "summary": "screen observe capacity",
    }
    if "target_allowlist" in input_mapping:
        intent["target_allowlist"] = dict(input_mapping["target_allowlist"])
    return intent


def _screen_control_intent(input_mapping: Mapping[str, Any]) -> dict[str, Any]:
    intent = {
        "action": "call_tool",
        "tool": "screen_control",
        "target_selector": dict(input_mapping["target_selector"]),
        "mode": "interactive",
        "execution_mode": input_mapping["execution_mode"],
        "actions": [dict(action) for action in input_mapping["actions"]],
        "summary": "screen control capacity",
    }
    if "target_allowlist" in input_mapping:
        intent["target_allowlist"] = dict(input_mapping["target_allowlist"])
    return intent


def _ref_to_dict(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    if isinstance(value, dict):
        return dict(value)
    return None


def _screen_observe_failure(api: InProcessServer, *, run_id: str) -> dict[str, str] | None:
    return _screen_action_failure(api, run_id=run_id)


def _screen_action_failure(api: InProcessServer, *, run_id: str) -> dict[str, str] | None:
    for event in reversed(api.get_events(run_id)):
        if event.event_type != "action.failed":
            continue
        error = event.payload.get("structured_error")
        if not isinstance(error, dict):
            continue
        reason_code = error.get("reason_code")
        message = error.get("message")
        if not isinstance(reason_code, str) or not reason_code:
            reason_code = "screen_action_failed"
        if not isinstance(message, str) or not message:
            message = "screen action failed"
        return {
            "reason_code": reason_code,
            "message": message,
        }
    return None
