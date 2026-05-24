"""Minimal action type registry boundary for the Isotope v0.1 slice."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from ...capabilities.tools.terminal import default_terminal_capabilities
from ...execution.screen_backend_types import (
    ALLOWED_CAPTURE_KINDS,
    ALLOWED_SCREEN_ACTION_TYPES,
    SUPPORTED_EXECUTION_MODES,
    SUPPORTED_SCREEN_MODES,
)


@dataclass(frozen=True)
class ActionTypeEntry:
    action_type: str
    tool_name: str
    payload_requirements: dict[str, Any]
    required_capabilities: dict[str, Any]
    default_workspace_mode: str
    result_kind: str
    enabled: bool

    @classmethod
    def from_dict(cls, entry: dict[str, Any]) -> "ActionTypeEntry":
        if not isinstance(entry, dict):
            raise ValueError("registry entry must be a dict")

        action_type = _required_string(entry, "action_type")
        tool_name = _required_string(entry, "tool_name")
        payload_requirements = entry.get("payload_requirements", {})
        if not isinstance(payload_requirements, dict):
            raise ValueError("payload_requirements must be a dict")
        required_capabilities = entry.get("required_capabilities")
        if not isinstance(required_capabilities, dict):
            raise ValueError("required_capabilities must be a dict")
        terminal_capabilities = required_capabilities.get("terminal")
        if terminal_capabilities is not None:
            _validate_terminal_capabilities(terminal_capabilities)
        screen_capabilities = required_capabilities.get("screen")
        if screen_capabilities is not None:
            _validate_screen_capabilities(screen_capabilities)
        default_workspace_mode = _required_string(entry, "default_workspace_mode")
        result_kind = _required_string(entry, "result_kind")
        enabled = entry.get("enabled")
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be a bool")

        return cls(
            action_type=action_type,
            tool_name=tool_name,
            payload_requirements=deepcopy(payload_requirements),
            required_capabilities=deepcopy(required_capabilities),
            default_workspace_mode=default_workspace_mode,
            result_kind=result_kind,
            enabled=enabled,
        )


class ActionTypeRegistry:
    """Small fixed registry for current v0 action/tool metadata."""

    def __init__(
        self,
        entries: list[dict[str, Any]] | None = None,
        *,
        registry_id: str = "default",
        registry_version: str = "v0.2",
    ) -> None:
        self.registry_id = _metadata_string("registry_id", registry_id)
        self.registry_version = _metadata_string("registry_version", registry_version)
        self._entries_by_tool: dict[str, ActionTypeEntry] = {}
        for raw_entry in entries or []:
            entry = ActionTypeEntry.from_dict(raw_entry)
            self._entries_by_tool[entry.tool_name] = entry

    @classmethod
    def default(
        cls,
        *,
        enable_codex_task: bool = False,
        codex_task_budget_seconds: int | None = None,
    ) -> "ActionTypeRegistry":
        entries = [
            _write_artifact_tool_entry(),
            _terminal_exec_tool_entry(),
            _screen_observe_tool_entry(),
            _screen_control_tool_entry(),
        ]
        if enable_codex_task:
            codex_entry = _codex_task_tool_entry()
            if codex_task_budget_seconds is not None:
                _validate_budget_seconds("codex_task_budget_seconds", codex_task_budget_seconds)
                codex_entry["required_capabilities"]["budget"]["seconds"] = codex_task_budget_seconds
            entries.append(codex_entry)
        return cls(
            entries=entries,
            registry_id="default",
            registry_version="v0.2",
        )

    def tool_names(self) -> list[str]:
        return list(self._entries_by_tool.keys())

    def get_tool(self, tool_name: str) -> ActionTypeEntry:
        try:
            return self._entries_by_tool[tool_name]
        except KeyError as exc:
            raise KeyError(tool_name) from exc

    def is_deferred_tool(self, tool_name: str) -> bool:
        return tool_name not in self._entries_by_tool and any(
            entry["name"] == tool_name for entry in _deferred_model_tool_entries()
        )

    def model_tool_catalog(self) -> dict[str, Any]:
        """Return the model-facing callable tool catalog without executable hooks."""
        return {
            "version": "model-tool-catalog.v0.1",
            "registry_id": self.registry_id,
            "registry_version": self.registry_version,
            "tools": [
                _model_tool_entry(entry)
                for entry in self._entries_by_tool.values()
                if entry.enabled
            ],
            "deferred_tools": [
                entry
                for entry in _deferred_model_tool_entries()
                if entry["name"] not in self._entries_by_tool
            ],
        }


def _required_string(entry: dict[str, Any], field_name: str) -> str:
    value = entry.get(field_name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _metadata_string(field_name: str, value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _validate_terminal_capabilities(capabilities: Any) -> None:
    if not isinstance(capabilities, dict):
        raise ValueError("terminal capabilities must be a dict")
    allowed_commands = capabilities.get("allowed_commands", [])
    if not isinstance(allowed_commands, list) or not all(
        isinstance(command, str) and command for command in allowed_commands
    ):
        raise ValueError("terminal.allowed_commands must be a list of non-empty strings")
    approval_required = capabilities.get("approval_required_commands", [])
    if not isinstance(approval_required, list) or not all(
        isinstance(command, str) and command for command in approval_required
    ):
        raise ValueError("terminal.approval_required_commands must be a list of non-empty strings")


def _validate_screen_capabilities(capabilities: Any) -> None:
    if not isinstance(capabilities, dict):
        raise ValueError("screen capabilities must be a dict")
    if not isinstance(capabilities.get("observe"), bool):
        raise ValueError("screen.observe must be a bool")
    if not isinstance(capabilities.get("control"), bool):
        raise ValueError("screen.control must be a bool")
    _validate_target_selector_policy(capabilities.get("target_selector_policy", {}))
    _validate_action_policy(capabilities.get("action_policy", {}))
    _validate_artifact_policy(capabilities.get("artifact_policy", {}))


def _validate_target_selector_policy(policy: Any) -> None:
    if not isinstance(policy, dict):
        raise ValueError("screen.target_selector_policy must be a dict")
    for field_name in ("allowed_apps", "allowed_title_contains"):
        value = policy.get(field_name, [])
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError(f"screen.target_selector_policy.{field_name} must be a list of strings")


def _validate_action_policy(policy: Any) -> None:
    if not isinstance(policy, dict):
        raise ValueError("screen.action_policy must be a dict")
    execution_modes = policy.get("execution_modes", [])
    if not isinstance(execution_modes, list) or not all(
        isinstance(item, str) and item in SUPPORTED_EXECUTION_MODES for item in execution_modes
    ):
        raise ValueError("screen.action_policy.execution_modes must be supported strings")
    allowed_action_types = policy.get("allowed_action_types", [])
    if not isinstance(allowed_action_types, list) or not all(
        isinstance(item, str) and item in ALLOWED_SCREEN_ACTION_TYPES
        for item in allowed_action_types
    ):
        raise ValueError("screen.action_policy.allowed_action_types must be supported strings")
    allowed_buttons = policy.get("allowed_buttons", [])
    if not isinstance(allowed_buttons, list) or not all(isinstance(item, str) for item in allowed_buttons):
        raise ValueError("screen.action_policy.allowed_buttons must be a list of strings")
    max_actions = policy.get("max_actions", 0)
    if not isinstance(max_actions, int) or max_actions <= 0:
        raise ValueError("screen.action_policy.max_actions must be a positive integer")
    modes = policy.get("modes", [])
    if not isinstance(modes, list) or not all(
        isinstance(item, str) and item in SUPPORTED_SCREEN_MODES for item in modes
    ):
        raise ValueError("screen.action_policy.modes must be supported strings")


def _validate_artifact_policy(policy: Any) -> None:
    if not isinstance(policy, dict):
        raise ValueError("screen.artifact_policy must be a dict")
    capture = policy.get("capture", [])
    if not isinstance(capture, list) or not all(
        isinstance(item, str) and item in ALLOWED_CAPTURE_KINDS for item in capture
    ):
        raise ValueError("screen.artifact_policy.capture must be supported strings")
    for field_name in ("max_screenshot_bytes", "max_screenshot_width", "max_screenshot_height"):
        value = policy.get(field_name)
        if not isinstance(value, int) or value <= 0:
            raise ValueError(f"screen.artifact_policy.{field_name} must be a positive integer")
    for field_name in ("full_content_in_events", "full_content_in_read_model"):
        if policy.get(field_name) is not False:
            raise ValueError(f"screen.artifact_policy.{field_name} must be false")


def _validate_budget_seconds(field_name: str, value: int) -> None:
    if not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")


def _write_artifact_tool_entry() -> dict[str, Any]:
    return {
        "action_type": "call_tool",
        "tool_name": "write_artifact_tool",
        "payload_requirements": {"required": ["text"]},
        "required_capabilities": {
            "tools": ["write_artifact_tool"],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": 30},
        },
        "default_workspace_mode": "shared_ro",
        "result_kind": "artifact",
        "enabled": True,
    }


def _terminal_exec_tool_entry() -> dict[str, Any]:
    return {
        "action_type": "call_tool",
        "tool_name": "terminal_exec",
        "payload_requirements": {"required": ["argv"]},
        "required_capabilities": {
            "tools": ["terminal_exec"],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": 5},
            "terminal": default_terminal_capabilities(),
        },
        "default_workspace_mode": "shared_ro",
        "result_kind": "terminal_output",
        "enabled": True,
    }


def _default_screen_artifact_policy() -> dict[str, Any]:
    return {
        "capture": ["screenshot", "metadata", "control_plan", "control_result", "diagnostic"],
        "max_screenshot_bytes": 500000,
        "max_screenshot_width": 1600,
        "max_screenshot_height": 1200,
        "full_content_in_events": False,
        "full_content_in_read_model": False,
    }


def _default_screen_action_policy(*, execution_modes: list[str]) -> dict[str, Any]:
    return {
        "modes": ["manual", "assist", "auto", "non_intrusive", "interactive"],
        "execution_modes": execution_modes,
        "allowed_action_types": [
            "move",
            "button_down",
            "button_up",
            "click",
            "wheel",
            "key_down",
            "key_up",
            "key_press",
        ],
        "allowed_buttons": ["left", "middle", "right", "x1", "x2"],
        "max_actions": 16,
    }


def _default_screen_target_selector_policy() -> dict[str, Any]:
    return {
        "allowed_apps": [],
        "allowed_title_contains": [],
    }


def _screen_observe_tool_entry() -> dict[str, Any]:
    return {
        "action_type": "call_tool",
        "tool_name": "screen_observe",
        "payload_requirements": {"required": ["target_selector"]},
        "required_capabilities": {
            "tools": ["screen_observe"],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": 5},
            "screen": {
                "observe": True,
                "control": False,
                "target_selector_policy": _default_screen_target_selector_policy(),
                "action_policy": _default_screen_action_policy(execution_modes=["dry_run"]),
                "artifact_policy": _default_screen_artifact_policy(),
            },
        },
        "default_workspace_mode": "shared_ro",
        "result_kind": "screen_observation",
        "enabled": True,
    }


def _screen_control_tool_entry() -> dict[str, Any]:
    return {
        "action_type": "call_tool",
        "tool_name": "screen_control",
        "payload_requirements": {"required": ["target_selector", "execution_mode", "actions"]},
        "required_capabilities": {
            "tools": ["screen_control"],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": 5},
            "screen": {
                "observe": True,
                "control": True,
                "target_selector_policy": _default_screen_target_selector_policy(),
                "action_policy": _default_screen_action_policy(execution_modes=["dry_run"]),
                "artifact_policy": _default_screen_artifact_policy(),
            },
        },
        "default_workspace_mode": "shared_ro",
        "result_kind": "screen_control_result",
        "enabled": True,
    }


def _codex_task_tool_entry() -> dict[str, Any]:
    return {
        "action_type": "delegate_agent_task",
        "tool_name": "codex_task",
        "payload_requirements": {"required": ["prompt"]},
        "required_capabilities": {
            "tools": ["codex_task"],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": 60},
            "codex_task": {"adapter_required": True},
        },
        "default_workspace_mode": "shared_ro",
        "result_kind": "agent_task_output",
        "enabled": True,
    }


def _model_tool_entry(entry: ActionTypeEntry) -> dict[str, Any]:
    capabilities = deepcopy(entry.required_capabilities)
    budget = capabilities.get("budget", {})
    budget_seconds = budget.get("seconds") if isinstance(budget, dict) else None
    tool: dict[str, Any] = {
        "name": entry.tool_name,
        "action": entry.action_type,
        "status": "enabled",
        "input_schema": _input_schema_from_payload_requirements(entry.payload_requirements),
        "constraints": {
            "workspace_mode": entry.default_workspace_mode,
            "budget_seconds": budget_seconds,
        },
        "output_contract": {
            "result_kind": entry.result_kind,
            "content_location": "artifact_ref",
            "full_content_in_events": False,
            "full_content_in_read_model": False,
        },
    }
    terminal = capabilities.get("terminal")
    if isinstance(terminal, dict):
        tool["constraints"].update({
            "shell": terminal.get("shell", False),
            "argv_policy": terminal.get("argv_policy", "allowlist"),
            "allowed_commands": list(terminal.get("allowed_commands", [])),
            "approval_required_commands": list(terminal.get("approval_required_commands", [])),
            "max_output_bytes": terminal.get("max_output_bytes"),
        })
    screen = capabilities.get("screen")
    if isinstance(screen, dict):
        artifact_policy = screen.get("artifact_policy", {})
        action_policy = screen.get("action_policy", {})
        tool["constraints"].update({
            "screen_observe": screen.get("observe", False),
            "screen_control": screen.get("control", False),
            "screen_modes": list(action_policy.get("modes", []))
            if isinstance(action_policy, dict)
            else [],
            "screen_execution_modes": list(action_policy.get("execution_modes", []))
            if isinstance(action_policy, dict)
            else [],
            "full_content_in_events": artifact_policy.get("full_content_in_events", False)
            if isinstance(artifact_policy, dict)
            else False,
        })
    codex = capabilities.get("codex_task")
    if isinstance(codex, dict):
        tool["constraints"].update({
            "terminal_tool": False,
            "uses_terminal_exec": False,
            "requires_selected_adapter": codex.get("adapter_required", True),
            "requires_approval": True,
        })
    return tool


def _input_schema_from_payload_requirements(payload_requirements: dict[str, Any]) -> dict[str, Any]:
    required = payload_requirements.get("required", [])
    properties: dict[str, Any] = {}
    for field_name in required:
        if field_name == "argv":
            properties[field_name] = {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
            }
        else:
            properties[field_name] = {"type": "string"}
    return {
        "type": "object",
        "required": list(required),
        "properties": properties,
    }


def _deferred_model_tool_entries() -> list[dict[str, Any]]:
    return [
        {
            "name": "codex_task",
            "action": "delegate_agent_task",
            "tool_kind": "agent_cli_task",
            "status": "deferred",
            "reason": "future agent CLI tool; requires explicit Codex adapter boundary",
            "input_schema": {
                "type": "object",
                "required": ["prompt"],
                "properties": {
                    "prompt": {"type": "string", "minLength": 1},
                },
            },
            "constraints": {
                "terminal_tool": False,
                "uses_terminal_exec": False,
                "requires_selected_adapter": True,
                "requires_approval": True,
                "full_content_in_events": False,
            },
            "output_contract": {
                "result_kind": "agent_task_output",
                "content_location": "artifact_ref",
                "full_content_in_events": False,
                "full_content_in_read_model": False,
            },
        }
    ]


__all__ = ["ActionTypeEntry", "ActionTypeRegistry"]
