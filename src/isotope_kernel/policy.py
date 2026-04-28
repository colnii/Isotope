"""Policy engine boundary for the Isotope v0.1 slice."""

from __future__ import annotations

from .action_registry import ActionTypeRegistry
from .ids import new_id
from .models import ActionProposal, PolicyDecision


class PolicyEngine:
    """Minimal policy boundary backed by action/tool metadata."""

    def __init__(self, registry: ActionTypeRegistry | None = None) -> None:
        self.registry = registry if registry is not None else ActionTypeRegistry.default()

    def decide(self, proposal: ActionProposal) -> PolicyDecision:
        budget_seconds = self._validate_proposal(proposal)
        requested_tools = proposal.requested_capabilities.get("tools", [])
        requested_workspace = proposal.requested_capabilities.get("workspace", {})

        if not isinstance(proposal.action_type, str) or proposal.action_type != "call_tool":
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
        ))

    def _denied(self, proposal: ActionProposal, reason_code: str) -> PolicyDecision:
        return self._validated_decision(PolicyDecision(
            decision_id=new_id("dec"),
            proposal_id=proposal.proposal_id,
            outcome="denied",
            grants={"tools": [], "workspace": {"mode": "none"}, "budget": {"seconds": 0}},
            reason_codes=[reason_code],
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
