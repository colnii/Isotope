"""Minimal action type registry boundary for the Isotope v0.1 slice."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any


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
    def default(cls) -> "ActionTypeRegistry":
        return cls(
            entries=[_write_artifact_tool_entry()],
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


def _required_string(entry: dict[str, Any], field_name: str) -> str:
    value = entry.get(field_name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _metadata_string(field_name: str, value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


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


__all__ = ["ActionTypeEntry", "ActionTypeRegistry"]
