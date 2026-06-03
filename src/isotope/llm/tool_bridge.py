"""Deterministic model-tool call bridge for in-process app spikes."""

from __future__ import annotations

from typing import Any

from ..platform.errors import IsotopeError
from ..capabilities.tools.terminal import validate_argv

_KERNEL_ERROR_CATEGORIES = {
    "validation",
    "not_found",
    "conflict",
    "not_enabled",
    "policy",
    "lifecycle",
    "internal",
}
_ERROR_SHAPE_KEYS = {"code", "message", "category", "retryable", "details"}


def submit_model_tool_call(
    app: Any,
    run_id: str,
    call: dict[str, Any],
    *,
    complete_run: bool = True,
) -> dict[str, Any]:
    """Submit a model-selected tool call through an explicit in-process route.

    This first slice is intentionally not a real LLM loop. The caller supplies a
    deterministic model decision, and the bridge verifies that the tool appears
    in the current model-facing catalog before routing it.
    """

    _require_non_empty_string("run_id", run_id)
    if not isinstance(complete_run, bool):
        raise _invalid_call("complete_run", "complete_run must be a bool")
    if not isinstance(call, dict):
        raise _invalid_call("call", "model tool call must be a JSON object")
    tool_name = _require_non_empty_string("tool_name", call.get("tool_name"))
    arguments = call.get("arguments")
    if not isinstance(arguments, dict):
        raise _invalid_call("arguments", "arguments must be a JSON object")

    catalog = app.server.get_model_tool_catalog()
    enabled_tools = {
        tool["name"]: tool
        for tool in catalog.get("tools", [])
        if isinstance(tool, dict) and isinstance(tool.get("name"), str)
    }
    if tool_name not in enabled_tools:
        if any(
            isinstance(tool, dict) and tool.get("name") == tool_name
            for tool in catalog.get("deferred_tools", [])
        ):
            raise IsotopeError(
                f"model tool {tool_name} is not enabled",
                code="model_tool_not_enabled",
                category="not_enabled",
                retryable=False,
                http_status=501,
                details={"tool_name": tool_name},
            )
        raise IsotopeError(
            f"unknown model tool {tool_name}",
            code="unknown_model_tool",
            category="validation",
            retryable=False,
            http_status=400,
            details={"tool_name": tool_name},
        )

    if tool_name == "terminal_exec":
        return _submit_terminal_exec_tool_call(
            app,
            run_id,
            arguments,
            catalog_entry=enabled_tools[tool_name],
            complete_run=complete_run,
        )

    if tool_name != "codex_task":
        raise IsotopeError(
            f"model tool {tool_name} does not have an enabled bridge route",
            code="model_tool_route_not_enabled",
            category="not_enabled",
            retryable=False,
            http_status=501,
            details={"tool_name": tool_name},
        )

    route = f"/runs/{run_id}/codex-tasks"
    response = app.request(
        "POST",
        route,
        json=_codex_task_body(call, arguments, complete_run=complete_run),
    )
    body = response.json()
    if response.status_code >= 400:
        _raise_http_error(body, response.status_code)
    return _safe_result(
        tool_name=tool_name,
        route=route,
        status_code=response.status_code,
        body=body,
    )


def _submit_terminal_exec_tool_call(
    app: Any,
    run_id: str,
    arguments: dict[str, Any],
    *,
    catalog_entry: dict[str, Any],
    complete_run: bool,
) -> dict[str, Any]:
    intent = _terminal_exec_intent(arguments)
    requires_approval = _terminal_exec_requires_approval(
        intent["argv"],
        arguments,
        catalog_entry,
    )
    try:
        body = app.server.submit_action(
            run_id,
            intent,
            requires_approval=requires_approval,
            complete_run=complete_run,
        )
    except IsotopeError:
        raise
    except ValueError as exc:
        raise _invalid_call("arguments", str(exc)) from exc
    except PermissionError as exc:
        raise IsotopeError(
            str(exc),
            code="model_tool_policy_denied",
            category="policy",
            retryable=False,
            http_status=403,
            details={"tool_name": "terminal_exec"},
        ) from exc
    return _safe_direct_action_result(
        tool_name="terminal_exec",
        route="in-process:submit_action",
        body=body,
        requires_approval=requires_approval,
    )


def _terminal_exec_requires_approval(
    argv: list[str],
    arguments: dict[str, Any],
    catalog_entry: dict[str, Any],
) -> bool:
    if "requires_approval" in arguments and not isinstance(arguments["requires_approval"], bool):
        raise _invalid_call("requires_approval", "terminal_exec requires_approval must be a bool")
    requested = arguments.get("requires_approval")
    constraints = catalog_entry.get("constraints", {})
    if not isinstance(constraints, dict):
        constraints = {}
    approval_required_commands = constraints.get("approval_required_commands", [])
    if not isinstance(approval_required_commands, list):
        approval_required_commands = []
    command_requires_approval = argv[0] in {
        command for command in approval_required_commands if isinstance(command, str)
    }
    if command_requires_approval:
        if requested is False:
            raise _invalid_call(
                "requires_approval",
                "terminal_exec command requires approval",
            )
        return True
    return requested is True


def _codex_task_body(
    call: dict[str, Any],
    arguments: dict[str, Any],
    *,
    complete_run: bool,
) -> dict[str, Any]:
    prompt = _require_non_empty_string("prompt", arguments.get("prompt"))
    body: dict[str, Any] = {"prompt": prompt}
    if "summary" in arguments:
        body["summary"] = _require_non_empty_string("summary", arguments.get("summary"))
    if "requires_approval" in arguments and arguments["requires_approval"] is not True:
        raise _invalid_call("requires_approval", "codex_task must require approval")
    if "idempotency_key" in call:
        body["idempotency_key"] = _require_non_empty_string(
            "idempotency_key",
            call.get("idempotency_key"),
        )
    if not complete_run:
        body["complete_run"] = False
    return body


def _terminal_exec_intent(arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        argv = validate_argv(arguments.get("argv"))
    except ValueError as exc:
        raise _invalid_call("argv", str(exc)) from exc
    intent: dict[str, Any] = {
        "action": "call_tool",
        "tool": "terminal_exec",
        "argv": argv,
    }
    if "summary" in arguments:
        intent["summary"] = _require_non_empty_string("summary", arguments.get("summary"))
    if "budget" in arguments:
        budget = arguments.get("budget")
        if not isinstance(budget, dict):
            raise _invalid_call("budget", "budget must be a JSON object")
        intent["budget"] = dict(budget)
    if "workspace_mode" in arguments:
        intent["workspace_mode"] = _require_non_empty_string(
            "workspace_mode",
            arguments.get("workspace_mode"),
        )
    return intent


def _safe_direct_action_result(
    *,
    tool_name: str,
    route: str,
    body: dict[str, Any],
    requires_approval: bool,
) -> dict[str, Any]:
    safe = {
        "status": body.get("status"),
        "tool_name": tool_name,
        "route": route,
        "requires_approval": requires_approval,
    }
    for key in (
        "approval_id",
        "proposal_id",
        "decision_id",
        "execution_id",
        "tool_execution_status",
        "run_state",
    ):
        if key in body:
            safe[key] = body[key]
    if "artifact_ref" in body:
        artifact_ref = body["artifact_ref"]
        safe["artifact_ref"] = (
            artifact_ref.to_dict()
            if callable(getattr(artifact_ref, "to_dict", None))
            else artifact_ref
        )
    return safe


def _safe_result(
    *,
    tool_name: str,
    route: str,
    status_code: int,
    body: dict[str, Any],
) -> dict[str, Any]:
    safe = {
        "status": body.get("status"),
        "tool_name": tool_name,
        "route": route,
        "http_status_code": status_code,
        "requires_approval": True,
    }
    for key in (
        "approval_id",
        "proposal_id",
        "decision_id",
        "execution_id",
        "tool_execution_status",
        "artifact_ref",
        "run_state",
    ):
        if key in body:
            safe[key] = body[key]
    return safe


def _raise_http_error(body: Any, status_code: int) -> None:
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            code = error.get("code")
            message = error.get("message")
            category = error.get("category")
            retryable = error.get("retryable")
            raise IsotopeError(
                message if isinstance(message, str) and message else "model tool route failed",
                code=code if isinstance(code, str) and code else "model_tool_route_failed",
                category=(
                    category
                    if isinstance(category, str) and category in _KERNEL_ERROR_CATEGORIES
                    else _category_from_status(status_code)
                ),
                retryable=retryable if isinstance(retryable, bool) else False,
                http_status=status_code,
                details=_safe_error_details(error),
            )
    raise IsotopeError(
        "model tool route failed",
        code="model_tool_route_failed",
        category=_category_from_status(status_code),
        retryable=False,
        http_status=status_code,
        details={},
    )


def _safe_error_details(error: dict[str, Any]) -> dict[str, Any]:
    details: dict[str, Any] = {}
    nested_details = error.get("details")
    if isinstance(nested_details, dict):
        details.update(_safe_metadata(nested_details))
    details.update(
        _safe_metadata(
            {
                key: value
                for key, value in error.items()
                if key not in _ERROR_SHAPE_KEYS
            }
        )
    )
    return details


def _safe_metadata(values: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in values.items()
        if _is_low_sensitive_metadata_value(value)
    }


def _is_low_sensitive_metadata_value(value: Any) -> bool:
    if value is None or isinstance(value, (str, int, float, bool)):
        return True
    if isinstance(value, list):
        return all(item is None or isinstance(item, (str, int, float, bool)) for item in value)
    return False


def _category_from_status(status_code: int) -> str:
    if status_code == 404:
        return "not_found"
    if status_code == 409:
        return "conflict"
    if status_code == 501:
        return "not_enabled"
    if status_code == 403:
        return "policy"
    if 400 <= status_code < 500:
        return "validation"
    return "internal"


def _require_non_empty_string(field_name: str, value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise _invalid_call(field_name, f"{field_name} must be a non-empty string")
    return value


def _invalid_call(field_name: str, message: str) -> IsotopeError:
    return IsotopeError(
        message,
        code="invalid_model_tool_call",
        category="validation",
        retryable=False,
        http_status=400,
        details={"field": field_name},
    )


__all__ = ["submit_model_tool_call"]
