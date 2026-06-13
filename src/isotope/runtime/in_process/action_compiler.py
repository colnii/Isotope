"""Action compiler boundary for the Isotope v0.1 slice."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ...capabilities.tools.terminal import TERMINAL_APPROVAL_MODES, validate_argv
from ...execution.screen.backend_types import (
    ALLOWED_CAPTURE_KINDS,
    SUPPORTED_EXECUTION_MODES,
    SUPPORTED_SCREEN_MODES,
    ScreenAction,
    ScreenTargetSelector,
)
from ...platform.ids import new_id
from ...platform.registry.actions import ActionTypeRegistry
from ...platform.schemas.actions import ActionProposal


SCREEN_CONTROL_APPROVAL_MODES = {"single_approval", "yolo"}


class ActionCompiler:
    """Compile compact model-facing intents into canonical proposals."""

    def __init__(self, registry: ActionTypeRegistry | None = None) -> None:
        self.registry = registry or ActionTypeRegistry.default()

    def compile(self, intent: dict[str, Any], runtime_context: dict[str, str]) -> ActionProposal:
        if not isinstance(intent, dict):
            raise ValueError("intent must be a dict")
        if not isinstance(runtime_context, dict):
            raise ValueError("runtime_context must be a dict")
        for field_name in ("run_id", "agent_id", "thread_id"):
            value = runtime_context.get(field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"runtime_context.{field_name} must be a non-empty string")

        action = intent.get("action")
        if not isinstance(action, str) or not action:
            raise ValueError("unsupported compact action")
        tool = intent.get("tool")
        if not isinstance(tool, str) or not tool:
            if action != "call_tool":
                raise ValueError("unsupported compact action")
            raise ValueError("compact intent requires a tool")
        try:
            registry_entry = self.registry.get_tool(tool)
        except KeyError as exc:
            raise ValueError(f"unknown tool {tool}") from exc
        if not registry_entry.enabled:
            raise ValueError(f"disabled tool {tool}")
        if action != registry_entry.action_type:
            raise ValueError("unsupported compact action")

        requested_tools = intent.get(
            "requested_tools",
            deepcopy(registry_entry.required_capabilities).get("tools", [tool]),
        )
        if not isinstance(requested_tools, list):
            raise ValueError("requested_tools must be a list")

        required_workspace = registry_entry.required_capabilities.get("workspace", {})
        workspace_mode = intent.get("workspace_mode", required_workspace.get("mode", "shared_ro"))
        if not isinstance(workspace_mode, str):
            raise ValueError("workspace_mode must be a string")

        budget = dict(intent.get(
            "budget",
            registry_entry.required_capabilities.get("budget", {"seconds": 30}),
        ))
        seconds = budget.get("seconds", 30)
        if not isinstance(seconds, int) or seconds < 0:
            raise ValueError("budget.seconds must be a non-negative integer")

        payload = self._payload_from_intent(intent, tool, registry_entry.payload_requirements)
        if tool == "terminal_exec":
            payload["argv"] = validate_argv(payload.get("argv"))
            payload.update(_terminal_exec_optional_payload(intent))
            payload["approval_requested"] = runtime_context.get("requires_approval") is True
        if tool == "codex_task":
            prompt = payload.get("prompt")
            if not isinstance(prompt, str) or not prompt:
                raise ValueError("codex_task prompt must be a non-empty string")
            payload["approval_requested"] = runtime_context.get("requires_approval") is True
        if tool == "write_memory":
            payload["approval_requested"] = runtime_context.get("requires_approval") is True
        if tool == "local_file_read":
            path = payload.get("path")
            if not isinstance(path, str) or not path.strip():
                raise ValueError("local_file_read path must be a non-empty string")
            payload["path"] = path.strip()
            max_excerpt_chars = intent.get("max_excerpt_chars", 2000)
            if not isinstance(max_excerpt_chars, int) or isinstance(max_excerpt_chars, bool):
                raise ValueError("local_file_read max_excerpt_chars must be an integer")
            if max_excerpt_chars < 1 or max_excerpt_chars > 8000:
                raise ValueError("local_file_read max_excerpt_chars must be between 1 and 8000")
            payload["max_excerpt_chars"] = max_excerpt_chars
            payload["approval_requested"] = runtime_context.get("requires_approval") is True
        if tool == "screen_observe":
            payload = self._screen_observe_payload(intent, tool)
            payload["approval_requested"] = runtime_context.get("requires_approval") is True
        if tool == "screen_control":
            payload = self._screen_control_payload(intent, tool)
            payload["approval_requested"] = runtime_context.get("requires_approval") is True
        return ActionProposal(
            proposal_id=new_id("prop"),
            run_id=runtime_context["run_id"],
            agent_id=runtime_context["agent_id"],
            thread_id=runtime_context["thread_id"],
            action_type=registry_entry.action_type,
            payload=payload,
            requested_capabilities={
                "tools": list(requested_tools),
                "workspace": {"mode": workspace_mode},
                "budget": budget,
            },
            registry_id=self.registry.registry_id,
            registry_version=self.registry.registry_version,
        )

    def _payload_from_intent(
        self,
        intent: dict[str, Any],
        tool: str,
        payload_requirements: dict[str, Any],
    ) -> dict[str, Any]:
        required_fields = payload_requirements.get("required", [])
        if not isinstance(required_fields, list):
            raise ValueError("payload_requirements.required must be a list")
        missing_fields = [
            field_name
            for field_name in required_fields
            if (
                not isinstance(field_name, str)
                or (field_name not in intent and field_name != "text")
            )
        ]
        if missing_fields:
            missing = ", ".join(str(field_name) for field_name in missing_fields)
            raise ValueError(f"missing required payload fields: {missing}")

        payload = {"tool": tool}
        for field_name in required_fields:
            payload[field_name] = deepcopy(intent.get(field_name, ""))
        if "summary" in intent:
            payload["summary"] = deepcopy(intent["summary"])
        if "quality" in intent:
            payload["quality"] = deepcopy(intent["quality"])
        if "scope" in intent:
            payload["scope"] = deepcopy(intent["scope"])
        if "supersedes" in intent:
            payload["supersedes"] = deepcopy(intent["supersedes"])
        return payload

    def _screen_observe_payload(self, intent: dict[str, Any], tool: str) -> dict[str, Any]:
        payload = {
            "tool": tool,
            "target_selector": _normalized_target_selector(intent.get("target_selector")),
            "mode": _normalized_screen_mode(intent.get("mode", "non_intrusive")),
            "capture": _normalized_capture(intent.get("capture", ["metadata", "screenshot"])),
        }
        if "target_allowlist" in intent:
            payload["target_allowlist"] = _normalized_target_allowlist(
                intent["target_allowlist"]
            )
        if "summary" in intent:
            payload["summary"] = deepcopy(intent["summary"])
        return payload

    def _screen_control_payload(self, intent: dict[str, Any], tool: str) -> dict[str, Any]:
        payload = {
            "tool": tool,
            "target_selector": _normalized_target_selector(intent.get("target_selector")),
            "mode": _normalized_screen_mode(intent.get("mode", "interactive")),
            "execution_mode": _normalized_execution_mode(intent.get("execution_mode")),
            "approval_mode": _normalized_screen_control_approval_mode(
                intent.get("approval_mode", "single_approval")
            ),
            "actions": _normalized_screen_actions(intent.get("actions")),
            "capture": _normalized_capture(intent.get("capture", ["control_plan", "control_result"])),
        }
        if "target_allowlist" in intent:
            payload["target_allowlist"] = _normalized_target_allowlist(
                intent["target_allowlist"]
            )
        if "summary" in intent:
            payload["summary"] = deepcopy(intent["summary"])
        return payload


def _normalized_target_selector(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("screen target_selector must be a dict")
    selector = value.get("selector")
    if not isinstance(selector, dict):
        raise ValueError("screen target_selector.selector must be a dict")
    normalized = ScreenTargetSelector(kind=value.get("kind"), selector=deepcopy(selector))
    return {
        "kind": normalized.kind,
        "selector": deepcopy(normalized.selector),
    }


def _normalized_target_allowlist(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("screen target_allowlist must be a dict")
    result = {
        "allowed_apps": _string_list(
            "screen target_allowlist.allowed_apps",
            value.get("allowed_apps", []),
        ),
        "allowed_title_contains": _string_list(
            "screen target_allowlist.allowed_title_contains",
            value.get("allowed_title_contains", []),
        ),
        "allow_first_match_execute": value.get("allow_first_match_execute") is True,
    }
    if not result["allowed_apps"] and not result["allowed_title_contains"]:
        raise ValueError("screen target_allowlist must include at least one allow rule")
    return result


def _string_list(field_name: str, value: Any) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"{field_name} must be a list of non-empty strings")
    return list(value)


def _normalized_screen_mode(value: Any) -> str:
    if not isinstance(value, str) or value not in SUPPORTED_SCREEN_MODES:
        raise ValueError("screen mode is not supported")
    return value


def _normalized_execution_mode(value: Any) -> str:
    if not isinstance(value, str) or value not in SUPPORTED_EXECUTION_MODES:
        raise ValueError("screen execution_mode is not supported")
    return value


def _normalized_screen_control_approval_mode(value: Any) -> str:
    if not isinstance(value, str) or value not in SCREEN_CONTROL_APPROVAL_MODES:
        raise ValueError("screen control approval_mode is not supported")
    return value


def _normalized_capture(value: Any) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError("screen capture must be a non-empty list")
    normalized = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or item not in ALLOWED_CAPTURE_KINDS:
            raise ValueError(f"screen capture[{index}] is not supported")
        normalized.append(item)
    return normalized


def _normalized_screen_actions(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ValueError("screen actions must be a non-empty list")
    return [ScreenAction.from_dict(action).to_dict() for action in value]


def _terminal_exec_optional_payload(intent: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    cwd = intent.get("cwd")
    if cwd is not None:
        if not isinstance(cwd, str) or not cwd.strip():
            raise ValueError("terminal_exec cwd must be a non-empty string")
        payload["cwd"] = cwd.strip()
    approval_mode = intent.get("terminal_approval_mode")
    if approval_mode is not None:
        if not isinstance(approval_mode, str) or approval_mode not in TERMINAL_APPROVAL_MODES:
            supported = ", ".join(TERMINAL_APPROVAL_MODES)
            raise ValueError(f"terminal_exec terminal_approval_mode must be one of: {supported}")
        payload["terminal_approval_mode"] = approval_mode
    allowed_commands = intent.get("terminal_allowed_commands")
    if allowed_commands is not None:
        if not isinstance(allowed_commands, list) or not all(
            isinstance(item, str) and item.strip() for item in allowed_commands
        ):
            raise ValueError("terminal_exec terminal_allowed_commands must be a list of strings")
        payload["terminal_allowed_commands"] = [item.strip() for item in allowed_commands]
    max_output_bytes = intent.get("terminal_max_output_bytes")
    if max_output_bytes is not None:
        if not isinstance(max_output_bytes, int) or isinstance(max_output_bytes, bool) or max_output_bytes <= 0:
            raise ValueError("terminal_exec terminal_max_output_bytes must be a positive integer")
        payload["terminal_max_output_bytes"] = max_output_bytes
    return payload
