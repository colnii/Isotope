"""Policy engine boundary for the Isotope v0.1 slice."""

from __future__ import annotations

from .ids import new_id
from .models import ActionProposal, PolicyDecision


class PolicyEngine:
    """Minimal fixed policy for the write_artifact_tool slice."""

    def decide(self, proposal: ActionProposal) -> PolicyDecision:
        budget_seconds = self._validate_proposal(proposal)
        requested_tools = proposal.requested_capabilities.get("tools", [])
        requested_workspace = proposal.requested_capabilities.get("workspace", {})

        if not isinstance(proposal.action_type, str) or proposal.action_type != "call_tool":
            return self._denied(proposal, "unsupported_action")
        if proposal.payload.get("tool") != "write_artifact_tool":
            return self._denied(proposal, "unsupported_tool")
        if "write_artifact_tool" not in requested_tools:
            return self._denied(proposal, "tool_not_requested")

        grants = {
            "tools": ["write_artifact_tool"],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": min(budget_seconds, 60)},
        }
        requested_matches = (
            requested_tools == grants["tools"]
            and requested_workspace.get("mode", "shared_ro") == "shared_ro"
            and budget_seconds <= grants["budget"]["seconds"]
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
