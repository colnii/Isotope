"""Action and policy decision schema shapes for the current slice."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ActionProposal:
    """Implementation shape for the v0.1 slice, not a permanent protocol."""

    proposal_id: str
    run_id: str
    agent_id: str
    thread_id: str
    action_type: str
    payload: dict[str, Any]
    requested_capabilities: dict[str, Any]
    registry_id: str = "default"
    registry_version: str = "v0.2"

    @property
    def registry_basis(self) -> dict[str, str]:
        return {
            "registry_id": self.registry_id,
            "registry_version": self.registry_version,
        }


@dataclass(frozen=True)
class PolicyDecision:
    """Minimal policy decision shape for the v0.1 slice."""

    decision_id: str
    proposal_id: str
    outcome: str
    grants: dict[str, Any]
    reason_codes: list[str]
    policy_profile_id: str = "default"
    policy_version: str = "v0.2"

    @property
    def policy_basis(self) -> dict[str, str]:
        return {
            "policy_profile_id": self.policy_profile_id,
            "policy_version": self.policy_version,
        }


@dataclass(frozen=True)
class ActionExecution:
    """Minimal execution result shape for the v0.1 slice."""

    execution_id: str
    proposal_id: str
    decision_id: str
    action_type: str
    status: str
    effective_grants_snapshot: dict[str, Any]
