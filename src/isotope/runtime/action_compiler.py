"""Action compiler boundary for the Isotope v0.1 slice."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..capabilities.tools.terminal import validate_argv
from ..platform.ids import new_id
from ..platform.registry.actions import ActionTypeRegistry
from ..platform.schemas.models import ActionProposal


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
            if self.registry.is_deferred_tool(tool):
                raise ValueError(f"deferred tool {tool} is not callable") from exc
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
            payload["approval_requested"] = runtime_context.get("requires_approval") is True
        if tool == "codex_task":
            prompt = payload.get("prompt")
            if not isinstance(prompt, str) or not prompt:
                raise ValueError("codex_task prompt must be a non-empty string")
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
        return payload
