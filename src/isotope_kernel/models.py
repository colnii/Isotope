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


@dataclass(frozen=True)
class MemoryRecord:
    """Slice-only memory record shape, not a permanent protocol."""

    memory_id: str
    scope: str
    content: dict[str, Any]
    summary: str
    source_refs: list[dict[str, Any]]
    provenance: dict[str, Any]
    created_at: str
    supersedes: list[str]
    quality: str

    def __post_init__(self) -> None:
        if self.scope not in {"thread", "run", "session"}:
            raise ValueError("scope must be one of thread, run, session")
        if not isinstance(self.content, dict):
            raise TypeError("content must be a structured dict")
        if not isinstance(self.source_refs, list):
            raise TypeError("source_refs must be a list")
        if not isinstance(self.provenance, dict):
            raise TypeError("provenance must be a dict")
        for field_name in ("run_id", "execution_id", "action_type"):
            value = self.provenance.get(field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"provenance.{field_name} must be a non-empty string")
