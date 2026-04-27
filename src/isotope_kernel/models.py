"""Slice-only implementation shapes for the Isotope v0.1 slice."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .refs import ResourceRef


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


@dataclass(frozen=True)
class PolicyDecision:
    """Minimal policy decision shape for the v0.1 slice."""

    decision_id: str
    proposal_id: str
    outcome: str
    grants: dict[str, Any]
    reason_codes: list[str]


@dataclass(frozen=True)
class ActionExecution:
    """Minimal execution result shape for the v0.1 slice."""

    execution_id: str
    proposal_id: str
    decision_id: str
    action_type: str
    status: str
    effective_grants_snapshot: dict[str, Any]


@dataclass(frozen=True)
class Artifact:
    """Minimal artifact shape for the v0.1 slice."""

    artifact_id: str
    run_id: str
    ref: ResourceRef
    artifact_type: str
    summary: str
    content: str
    provenance: dict[str, Any]
