"""Policy engine boundary for the Isotope v0.1 slice."""

from __future__ import annotations

from ..capabilities.tools.terminal import validate_argv
from ..platform.ids import new_id
from ..platform.registry.actions import ActionTypeRegistry
from ..platform.schemas.models import ActionProposal, PolicyDecision


class PolicyEngine:
    """Minimal policy boundary backed by action/tool metadata."""

    def __init__(
        self,
        registry: ActionTypeRegistry | None = None,
        *,
        policy_profile_id: str = "default",
        policy_version: str = "v0.2",
    ) -> None:
        self.registry = registry if registry is not None else ActionTypeRegistry.default()
        self.policy_profile_id = self._metadata_string("policy_profile_id", policy_profile_id)
        self.policy_version = self._metadata_string("policy_version", policy_version)

    def decide(self, proposal: ActionProposal) -> PolicyDecision:
        budget_seconds = self._validate_proposal(proposal)
        requested_tools = proposal.requested_capabilities.get("tools", [])
        requested_workspace = proposal.requested_capabilities.get("workspace", {})

        if not isinstance(proposal.action_type, str) or not proposal.action_type:
            return self._denied(proposal, "unsupported_action")
        tool_name = proposal.payload.get("tool")
        if not isinstance(tool_name, str) or not tool_name:
            return self._denied(proposal, "unsupported_tool")
        try:
            entry = self.registry.get_tool(tool_name)
        except KeyError:
            return self._denied(proposal, "unsupported_tool")
        if not entry.enabled:
            return self._denied(proposal, "disabled_tool")
        if entry.action_type != proposal.action_type:
            return self._denied(proposal, "unsupported_action")

        required_capabilities = entry.required_capabilities
        required_tools = required_capabilities.get("tools", [])
        if not isinstance(required_tools, list):
            raise ValueError("registry required_capabilities.tools must be a list")
        if tool_name not in required_tools:
            return self._denied(proposal, "tool_requirement_missing")
        if tool_name not in requested_tools:
            return self._denied(proposal, "tool_not_requested")

        required_budget = required_capabilities.get("budget", {})
        if not isinstance(required_budget, dict):
            raise ValueError("registry required_capabilities.budget must be a dict")
        try:
            budget_cap = int(required_budget.get("seconds", 30))
        except (TypeError, ValueError) as exc:
            raise ValueError("registry budget.seconds must be int-like") from exc
        if budget_cap < 0:
            raise ValueError("registry budget.seconds must be non-negative")

        grants = {
            "tools": [tool_name],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": min(budget_seconds, budget_cap)},
        }
        if tool_name == "terminal_exec":
            terminal_capabilities = required_capabilities.get("terminal")
            if not isinstance(terminal_capabilities, dict):
                raise ValueError("registry required_capabilities.terminal must be a dict")
            allowed_commands = terminal_capabilities.get("allowed_commands", [])
            if not isinstance(allowed_commands, list) or not all(
                isinstance(item, str) for item in allowed_commands
            ):
                raise ValueError("registry terminal.allowed_commands must be a list of strings")
            approval_required_commands = terminal_capabilities.get("approval_required_commands", [])
            if not isinstance(approval_required_commands, list) or not all(
                isinstance(item, str) for item in approval_required_commands
            ):
                raise ValueError("registry terminal.approval_required_commands must be a list of strings")
            argv = validate_argv(proposal.payload.get("argv"))
            command = argv[0]
            allowed_command_set = set(allowed_commands)
            approval_required_command_set = set(approval_required_commands)
            if command in approval_required_command_set and proposal.payload.get("approval_requested") is not True:
                return self._denied(proposal, "terminal_approval_required")
            if command not in allowed_command_set and command not in approval_required_command_set:
                return self._denied(proposal, "terminal_command_not_allowed")
            granted_commands = list(allowed_commands)
            if command in approval_required_command_set and command not in granted_commands:
                granted_commands.append(command)
            try:
                max_output_bytes = int(terminal_capabilities.get("max_output_bytes", 4096))
            except (TypeError, ValueError) as exc:
                raise ValueError("registry terminal.max_output_bytes must be int-like") from exc
            if max_output_bytes <= 0:
                raise ValueError("registry terminal.max_output_bytes must be positive")
            if terminal_capabilities.get("shell", False) is not False:
                raise ValueError("registry terminal.shell must be false")
            if terminal_capabilities.get("argv_policy", "allowlist") != "allowlist":
                raise ValueError("registry terminal.argv_policy must be allowlist")
            grants["terminal"] = {
                "shell": False,
                "argv_policy": "allowlist",
                "allowed_commands": granted_commands,
                "max_output_bytes": max_output_bytes,
            }
        if tool_name == "codex_task":
            codex_capabilities = required_capabilities.get("codex_task")
            if not isinstance(codex_capabilities, dict):
                raise ValueError("registry required_capabilities.codex_task must be a dict")
            prompt = proposal.payload.get("prompt")
            if not isinstance(prompt, str) or not prompt:
                return self._denied(proposal, "codex_task_prompt_required")
            if proposal.payload.get("approval_requested") is not True:
                return self._denied(proposal, "codex_task_approval_required")
            grants["codex_task"] = {
                "adapter_required": codex_capabilities.get("adapter_required", True) is True,
            }
        requested_matches = (
            requested_tools == grants["tools"]
            and requested_workspace.get("mode", "shared_ro") == "shared_ro"
            and budget_seconds <= budget_cap
        )
        return self._validated_decision(PolicyDecision(
            decision_id=new_id("dec"),
            proposal_id=proposal.proposal_id,
            outcome="approved" if requested_matches else "modified",
            grants=grants,
            reason_codes=[] if requested_matches else ["capabilities_reduced"],
            policy_profile_id=self.policy_profile_id,
            policy_version=self.policy_version,
        ))

    def _denied(self, proposal: ActionProposal, reason_code: str) -> PolicyDecision:
        return self._validated_decision(PolicyDecision(
            decision_id=new_id("dec"),
            proposal_id=proposal.proposal_id,
            outcome="denied",
            grants={"tools": [], "workspace": {"mode": "none"}, "budget": {"seconds": 0}},
            reason_codes=[reason_code],
            policy_profile_id=self.policy_profile_id,
            policy_version=self.policy_version,
        ))

    def _validate_proposal(self, proposal: ActionProposal) -> int:
        if not isinstance(proposal, ActionProposal):
            raise TypeError("PolicyEngine.decide requires an ActionProposal")
        if not isinstance(proposal.payload, dict):
            raise TypeError("proposal payload must be a dict")
        if not isinstance(proposal.requested_capabilities, dict):
            raise TypeError("requested_capabilities must be a dict")
        requested_tools = proposal.requested_capabilities.get("tools", [])
        if not isinstance(requested_tools, list):
            raise TypeError("requested tools must be a list")
        requested_workspace = proposal.requested_capabilities.get("workspace", {})
        if not isinstance(requested_workspace, dict):
            raise TypeError("requested workspace must be a dict")
        requested_budget = proposal.requested_capabilities.get("budget", {})
        if not isinstance(requested_budget, dict):
            raise TypeError("requested budget must be a dict")
        try:
            budget_seconds = int(requested_budget.get("seconds", 30))
        except (TypeError, ValueError) as exc:
            raise ValueError("budget.seconds must be int-like") from exc
        if budget_seconds < 0:
            raise ValueError("budget.seconds must be non-negative")
        return budget_seconds

    def _validated_decision(self, decision: PolicyDecision) -> PolicyDecision:
        if decision.outcome not in {"approved", "modified", "denied"}:
            raise ValueError("unknown policy decision outcome")
        if decision.outcome == "denied":
            if decision.grants.get("tools"):
                raise ValueError("denied decision cannot grant tools")
            if decision.grants.get("workspace", {}).get("mode") not in {None, "none"}:
                raise ValueError("denied decision cannot grant workspace")
            if int(decision.grants.get("budget", {}).get("seconds", 0)) > 0:
                raise ValueError("denied decision cannot grant positive budget")
            return decision

        if not isinstance(decision.grants.get("tools"), list):
            raise ValueError("approved or modified decision requires tools grant")
        if not decision.grants.get("workspace", {}).get("mode"):
            raise ValueError("approved or modified decision requires workspace.mode grant")
        if "seconds" not in decision.grants.get("budget", {}):
            raise ValueError("approved or modified decision requires budget.seconds grant")
        return decision

    def _metadata_string(self, field_name: str, value: str) -> str:
        if not isinstance(value, str) or not value:
            raise ValueError(f"{field_name} must be a non-empty string")
        return value
