"""Artifact helpers for the in-process runtime workspace boundary."""

from __future__ import annotations

from typing import Any

from ..platform.events.events import CanonicalEvent
from ..platform.schemas.refs import ResourceRef


SOURCE_ARTIFACT_TYPES = {
    "text",
    "research.report",
    "research.raw_transcript",
    "research.provider_trace",
}


class InProcessArtifactMixin:
    """Create and inspect low-sensitive artifact records."""

    def create_source_artifact(
        self,
        run_id: str,
        *,
        summary: str,
        content: str,
        artifact_type: str = "text",
        basis_refs: list[ResourceRef] | None = None,
        source_refs: list[ResourceRef] | None = None,
    ) -> dict[str, Any]:
        run = self._runtime_context_for_write_helper(run_id)
        self._validate_non_empty_string("summary", summary)
        self._validate_non_empty_string("content", content)
        if artifact_type not in SOURCE_ARTIFACT_TYPES:
            raise ValueError("artifact_type is not supported")
        basis_ref_payloads = self._validate_artifact_ref_list("basis_refs", basis_refs, run_id)
        source_ref_payloads = self._validate_artifact_ref_list("source_refs", source_refs, run_id)

        proposal = self.compiler.compile(
            {
                "action": "call_tool",
                "tool": "write_artifact_tool",
                "text": content,
                "summary": summary,
            },
            {
                "run_id": run_id,
                "agent_id": run["agent_id"],
                "thread_id": run["thread_id"],
            },
        )
        proposal.payload["artifact_type"] = artifact_type
        if basis_ref_payloads:
            proposal.payload["basis_refs"] = basis_ref_payloads
        if source_ref_payloads:
            proposal.payload["source_refs"] = source_ref_payloads
        self._append(
            run_id,
            "action.proposed",
            {
                "proposal_id": proposal.proposal_id,
                "agent_id": proposal.agent_id,
                "thread_id": proposal.thread_id,
                "action_type": proposal.action_type,
                "registry_id": proposal.registry_id,
                "registry_version": proposal.registry_version,
                "registry_basis": proposal.registry_basis,
            },
        )

        decision = self.policy.decide(proposal)
        self._append(
            run_id,
            "action.decided",
            {
                "decision_id": decision.decision_id,
                "proposal_id": decision.proposal_id,
                "outcome": decision.outcome,
                "reason_codes": list(decision.reason_codes),
                "policy_profile_id": decision.policy_profile_id,
                "policy_version": decision.policy_version,
                "policy_basis": decision.policy_basis,
            },
        )
        if decision.outcome == "denied":
            raise PermissionError("source artifact setup denied by policy")

        execution = self.executor.execute(decision, proposal)
        artifact_ref = self._completed_artifact_ref(run_id, execution.execution_id)
        if artifact_ref is None:
            raise RuntimeError("source artifact setup completed without artifact ref")
        artifact_metadata = self.artifact_store.get_metadata(artifact_ref, include_provenance=True)
        state = self.get_run_state(run_id)
        return {
            "status": execution.status,
            "proposal_id": proposal.proposal_id,
            "decision_id": decision.decision_id,
            "execution_id": execution.execution_id,
            "artifact_ref": artifact_ref,
            "artifact_summary": artifact_metadata["summary"],
            "artifact_type": artifact_metadata["artifact_type"],
            "provenance": dict(artifact_metadata["provenance"]),
            "basis_refs": [dict(ref) for ref in artifact_metadata.get("basis_refs", [])],
            "source_refs": [dict(ref) for ref in artifact_metadata.get("source_refs", [])],
            "run_state": state,
        }

    def get_artifact_record(self, ref: ResourceRef) -> dict[str, Any]:
        if not isinstance(ref, ResourceRef):
            raise TypeError("artifact record requires a structured ResourceRef")
        if ref.ref_type != "artifact":
            raise ValueError("artifact record requires an artifact ResourceRef")

        metadata = self.artifact_store.get_metadata(ref, include_provenance=True)
        basis_event = self._find_artifact_created_event(ref)
        if basis_event is None:
            raise ValueError("artifact.created event not found")
        record = {
            "artifact_id": ref.artifact_id,
            "artifact_type": metadata["artifact_type"],
            "summary": metadata["summary"],
            "ref": ref.to_dict(),
            "provenance": dict(metadata["provenance"]),
            "basis_event_id": basis_event.event_id,
            "basis_event_type": basis_event.event_type,
            "basis_created_at": basis_event.created_at,
        }
        artifact_payload = basis_event.payload["artifact"]
        for field_name in ("basis_refs", "source_refs"):
            refs = artifact_payload.get(field_name, metadata.get(field_name, []))
            if refs:
                record[field_name] = [dict(item) for item in refs]
        return record

    def _find_artifact_created_event(self, ref: ResourceRef) -> CanonicalEvent | None:
        expected_ref = ref.to_dict()
        for event in self.event_store.list_events(ref.run_id):
            if event.event_type != "artifact.created":
                continue
            artifact = event.payload.get("artifact")
            if not isinstance(artifact, dict):
                raise ValueError("malformed artifact.created event")
            if artifact.get("ref") == expected_ref:
                return event
        return None

    def _validate_artifact_ref_list(
        self,
        field_name: str,
        refs: list[ResourceRef] | None,
        run_id: str,
    ) -> list[dict[str, str]]:
        if refs is None:
            return []
        if not isinstance(refs, list):
            raise TypeError(f"{field_name} must be a list of structured ResourceRef")
        if not refs:
            raise ValueError(f"{field_name} must be a non-empty list when provided")
        payloads: list[dict[str, str]] = []
        for index, ref in enumerate(refs):
            if not isinstance(ref, ResourceRef):
                raise TypeError(f"{field_name}[{index}] must be a structured ResourceRef")
            if ref.ref_type != "artifact":
                raise ValueError(f"{field_name}[{index}] must be an artifact ResourceRef")
            if ref.run_id != run_id:
                raise ValueError(f"{field_name}[{index}] run_id must match run_id")
            self.get_artifact_record(ref)
            payloads.append(ref.to_dict())
        return payloads
