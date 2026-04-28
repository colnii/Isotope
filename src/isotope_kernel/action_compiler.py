"""Action compiler boundary for the Isotope v0.1 slice."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .action_registry import ActionTypeRegistry
from .ids import new_id
from .models import ActionProposal


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

        if intent.get("action") != "call_tool":
            raise ValueError("unsupported compact action")
        tool = intent.get("tool")
        if not isinstance(tool, str) or not tool:
            raise ValueError("compact intent requires a tool")
        try:
            registry_entry = self.registry.get_tool(tool)
        except KeyError as exc:
            raise ValueError(f"unknown tool {tool}") from exc
        if not registry_entry.enabled:
            raise ValueError(f"disabled tool {tool}")

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

        return ActionProposal(
            proposal_id=new_id("prop"),
            run_id=runtime_context["run_id"],
            agent_id=runtime_context["agent_id"],
            thread_id=runtime_context["thread_id"],
            action_type=registry_entry.action_type,
            payload={
                "tool": tool,
                "text": intent.get("text", ""),
            },
            requested_capabilities={
                "tools": list(requested_tools),
                "workspace": {"mode": workspace_mode},
                "budget": budget,
            },
        )
