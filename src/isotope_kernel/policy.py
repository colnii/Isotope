"""Policy engine boundary for the Isotope v0.1 slice."""

from __future__ import annotations

from .ids import new_id
from .models import ActionProposal, PolicyDecision


class PolicyEngine:
    """Minimal fixed policy for the write_artifact_tool slice."""

    def decide(self, proposal: ActionProposal) -> PolicyDecision:
        requested_tools = proposal.requested_capabilities.get("tools", [])
        requested_workspace = proposal.requested_capabilities.get("workspace", {})
        requested_budget = proposal.requested_capabilities.get("budget", {})

        if proposal.action_type != "call_tool":
            return self._denied(proposal, "unsupported_action")
        if proposal.payload.get("tool") != "write_artifact_tool":
            return self._denied(proposal, "unsupported_tool")
        if "write_artifact_tool" not in requested_tools:
            return self._denied(proposal, "tool_not_requested")

        grants = {
            "tools": ["write_artifact_tool"],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": min(int(requested_budget.get("seconds", 30)), 60)},
        }
        requested_matches = (
            requested_tools == grants["tools"]
            and requested_workspace.get("mode", "shared_ro") == "shared_ro"
            and int(requested_budget.get("seconds", 30)) <= grants["budget"]["seconds"]
        )
        return PolicyDecision(
            decision_id=new_id("dec"),
            proposal_id=proposal.proposal_id,
            outcome="approved" if requested_matches else "modified",
            grants=grants,
            reason_codes=[] if requested_matches else ["capabilities_reduced"],
        )

    def _denied(self, proposal: ActionProposal, reason_code: str) -> PolicyDecision:
        return PolicyDecision(
            decision_id=new_id("dec"),
            proposal_id=proposal.proposal_id,
            outcome="denied",
            grants={"tools": [], "workspace": {"mode": "none"}, "budget": {"seconds": 0}},
            reason_codes=[reason_code],
        )
