"""Workspace, artifact, and worker handoff helpers for the in-process runtime."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..platform.errors import IsotopeError, IsotopePermissionError
from ..platform.ids import new_id
from ..platform.schemas.actions import PolicyDecision
from ..platform.schemas.refs import ResourceRef
from ..platform.state.projector import RunProjector


class InProcessWorkspaceMixin:
    """Manage runtime workspace bindings, artifacts, and worker handoffs."""

    def bind_workspace(
        self,
        run_id: str,
        decision: PolicyDecision,
        bound_to: dict[str, Any] | None = None,
        lease_status: str = "active",
    ) -> dict[str, Any]:
        self._validate_existing_run_id(run_id)
        if not isinstance(decision, PolicyDecision):
            raise TypeError("decision must be a PolicyDecision")
        if bound_to is None:
            bound_to = {"agent_id": self._runs[run_id]["agent_id"]}
        if not isinstance(bound_to, dict) or not bound_to:
            raise ValueError("bound_to must be a non-empty dict")
        has_binding_subject = any(
            isinstance(bound_to.get(field), str) and bound_to.get(field)
            for field in ("agent_id", "execution_id")
        )
        if not has_binding_subject:
            raise ValueError("bound_to must include agent_id or execution_id")
        if lease_status not in {"active", "released"}:
            raise ValueError("lease_status must be active or released")

        binding = self.workspace_manager.get_binding(decision.grants)
        workspace_grant = decision.grants["workspace"]
        event = self._append(
            run_id,
            "workspace.bound",
            {
                "workspace_id": binding.workspace_id,
                "run_id": run_id,
                "mode": binding.mode,
                "bound_to": dict(bound_to),
                "lease_status": lease_status,
                "provenance": {
                    "decision_id": decision.decision_id,
                    "grant_basis": {
                        "workspace": dict(workspace_grant),
                    },
                },
            },
        )
        state = self.get_run_state(run_id)
        workspace_binding = state.workspaces.get(binding.workspace_id)
        if workspace_binding is None:
            raise RuntimeError(f"workspace binding was not projected from {event.event_id}")
        return deepcopy(workspace_binding)

    def create_workspace_lease(
        self,
        run_id: str,
        decision: PolicyDecision,
        *,
        created_by: dict[str, Any],
        bound_to: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._validate_existing_run_id(run_id)
        if not isinstance(decision, PolicyDecision):
            raise TypeError("decision must be a PolicyDecision")
        if not isinstance(created_by, dict) or not any(
            isinstance(created_by.get(field), str) and created_by[field]
            for field in ("proposal_id", "execution_id")
        ):
            raise ValueError("created_by must include proposal_id or execution_id")
        if bound_to is None:
            bound_to = {"agent_id": self._runs[run_id]["agent_id"]}
        if not isinstance(bound_to, dict) or not any(
            isinstance(bound_to.get(field), str) and bound_to[field]
            for field in ("agent_id", "execution_id", "worker_id")
        ):
            raise ValueError("bound_to must include agent_id, execution_id, or worker_id")

        binding = self.workspace_manager.get_binding(decision.grants)
        workspace_grant = decision.grants["workspace"]
        event = self._build_event(
            run_id,
            "workspace.lease_created",
            {
                "workspace_id": binding.workspace_id,
                "run_id": run_id,
                "mode": binding.mode,
                "lease_status": "created",
                "bound_to": dict(bound_to),
                "granted_by": {"decision_id": decision.decision_id},
                "created_by": dict(created_by),
                "provenance": {
                    "decision_id": decision.decision_id,
                    "grant_basis": {"workspace": dict(workspace_grant)},
                },
            },
        )
        self._project_with_candidate(run_id, event)
        appended = self.event_store.append(event)
        workspace_entry = self.get_run_state(run_id).workspaces.get(binding.workspace_id)
        if workspace_entry is None:
            raise RuntimeError(f"workspace lease was not projected from {appended.event_id}")
        return deepcopy(workspace_entry)

    def capture_workspace_artifact(
        self,
        run_id: str,
        *,
        workspace_id: str,
        artifact_ref: ResourceRef,
        captured_by: dict[str, Any],
    ) -> dict[str, Any]:
        self._validate_existing_run_id(run_id)
        self._validate_non_empty_string("workspace_id", workspace_id)
        if not isinstance(artifact_ref, ResourceRef):
            raise TypeError("artifact_ref must be a structured ResourceRef")
        if artifact_ref.run_id != run_id:
            raise ValueError("artifact_ref run_id must match run_id")
        if not isinstance(captured_by, dict) or not any(
            isinstance(captured_by.get(field), str) and captured_by[field]
            for field in ("execution_id", "agent_id", "worker_id")
        ):
            raise ValueError("captured_by must include execution_id, agent_id, or worker_id")

        artifact_record = self.get_artifact_record(artifact_ref)
        event = self._build_event(
            run_id,
            "workspace.artifact_captured",
            {
                "workspace_id": workspace_id,
                "run_id": run_id,
                "artifact_ref": artifact_ref.to_dict(),
                "captured_by": dict(captured_by),
                "provenance": {
                    "artifact_event_id": artifact_record["basis_event_id"],
                    "basis_event_id": artifact_record["basis_event_id"],
                    "decision_id": artifact_record["provenance"].get("decision_id"),
                },
            },
        )
        self._project_with_candidate(run_id, event)
        appended = self.event_store.append(event)
        workspace_entry = self.get_run_state(run_id).workspaces.get(workspace_id)
        if workspace_entry is None:
            raise RuntimeError(f"workspace capture was not projected from {appended.event_id}")
        return {
            "status": "captured",
            "workspace_id": workspace_id,
            "artifact_ref": artifact_ref.to_dict(),
            "basis_event_id": appended.event_id,
            "workspace": deepcopy(workspace_entry),
            "private_append_required": False,
        }

    def release_workspace(
        self,
        run_id: str,
        *,
        workspace_id: str,
        released_by: dict[str, Any],
        reason: str,
    ) -> dict[str, Any]:
        self._validate_existing_run_id(run_id)
        self._validate_non_empty_string("workspace_id", workspace_id)
        self._validate_non_empty_string("reason", reason)
        if not isinstance(released_by, dict) or not any(
            isinstance(released_by.get(field), str) and released_by[field]
            for field in ("agent_id", "execution_id", "worker_id", "system")
        ):
            raise ValueError("released_by must identify a release actor")
        state = self.get_run_state(run_id)
        workspace_entry = state.workspaces.get(workspace_id)
        if workspace_entry is None:
            raise ValueError("unknown workspace")

        event = self._build_event(
            run_id,
            "workspace.released",
            {
                "workspace_id": workspace_id,
                "run_id": run_id,
                "lease_status": "released",
                "released_by": dict(released_by),
                "released_at": "2026-04-27T00:00:00Z",
                "reason": reason,
                "basis_event_id": workspace_entry["last_event_id"],
            },
        )
        self._project_with_candidate(run_id, event)
        appended = self.event_store.append(event)
        released_workspace = self.get_run_state(run_id).workspaces.get(workspace_id)
        if released_workspace is None:
            raise RuntimeError(f"workspace release was not projected from {appended.event_id}")
        return {
            "status": "released",
            "workspace_id": workspace_id,
            "basis_event_id": appended.event_id,
            "workspace": deepcopy(released_workspace),
            "private_append_required": False,
        }

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
        if artifact_type != "text":
            raise ValueError("artifact_type must be text")
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

    def submit_worker_handoff(
        self,
        run_id: str,
        *,
        delegation_intent: dict[str, Any],
        artifact_ref: ResourceRef,
        summary: str,
    ) -> dict[str, Any]:
        self._runtime_context_for_write_helper(run_id)
        intent = self._validate_worker_handoff_intent(delegation_intent)
        self._validate_non_empty_string("summary", summary)
        try:
            artifact_record = self.get_artifact_record(artifact_ref)
        except FileNotFoundError as exc:
            artifact_id = getattr(artifact_ref, "artifact_id", None)
            artifact_run_id = getattr(artifact_ref, "run_id", None)
            raise IsotopeError(
                "unknown artifact ResourceRef",
                code="worker_handoff_unknown_artifact",
                category="not_found",
                retryable=False,
                http_status=404,
                details={"run_id": artifact_run_id, "artifact_id": artifact_id},
            ) from exc
        if artifact_ref.run_id != run_id:
            raise IsotopeError(
                "artifact_ref run_id must match run_id",
                code="worker_handoff_invalid_artifact_ref",
                category="validation",
                retryable=False,
                http_status=400,
                details={"run_id": run_id, "artifact_run_id": artifact_ref.run_id},
            )

        delegation_id = new_id("deleg")
        decision_id = new_id("dec")
        grants, outcome, reason_codes = self._derive_worker_handoff_grants(intent["requested_capabilities"])
        decision_events = [
            self._build_event(
                run_id,
                "delegation.proposed",
                {
                    "delegation_id": delegation_id,
                    "run_id": run_id,
                    "parent_agent_id": intent["parent_agent_id"],
                    "requested_worker_role": intent["requested_worker_role"],
                    "requested_capabilities": deepcopy(intent["requested_capabilities"]),
                },
            ),
            self._build_event(
                run_id,
                "delegation.decided",
                {
                    "delegation_id": delegation_id,
                    "decision_id": decision_id,
                    "outcome": outcome,
                    "grants": deepcopy(grants),
                    "reason_codes": reason_codes,
                    "policy_profile_id": self.policy.policy_profile_id,
                    "policy_version": self.policy.policy_version,
                    "policy_basis": {
                        "policy_profile_id": self.policy.policy_profile_id,
                        "policy_version": self.policy.policy_version,
                    },
                },
            ),
        ]
        if outcome == "denied":
            existing_events = self.event_store.list_events(run_id)
            RunProjector().project([*existing_events, *decision_events])
            for event in decision_events:
                self.event_store.append(event)
            raise IsotopePermissionError(
                "worker handoff denied by policy",
                code="worker_handoff_denied",
                category="policy",
                retryable=False,
                http_status=403,
                details={"reason_codes": list(reason_codes)},
            )

        worker_id = new_id("worker")
        agent_id = new_id("agent_worker")
        candidate_events = [
            *decision_events,
            self._build_event(
                run_id,
                "worker.created",
                {
                    "worker_id": worker_id,
                    "agent_id": agent_id,
                    "run_id": run_id,
                    "parent_agent_id": intent["parent_agent_id"],
                    "delegation_id": delegation_id,
                    "decision_id": decision_id,
                    "role": intent["requested_worker_role"],
                    "status": "created",
                    "workspace": dict(grants["workspace"]),
                },
            ),
            self._build_event(
                run_id,
                "worker.started",
                {
                    "worker_id": worker_id,
                    "delegation_id": delegation_id,
                    "status": "running",
                },
            ),
            self._build_event(
                run_id,
                "worker.result_handed_off",
                {
                    "worker_id": worker_id,
                    "delegation_id": delegation_id,
                    "artifact_ref": artifact_ref.to_dict(),
                    "summary": summary,
                    "provenance": {
                        "artifact_basis_event_id": artifact_record["basis_event_id"],
                    },
                },
            ),
            self._build_event(
                run_id,
                "worker.completed",
                {
                    "worker_id": worker_id,
                    "delegation_id": delegation_id,
                    "status": "completed",
                },
            ),
        ]

        existing_events = self.event_store.list_events(run_id)
        projected = RunProjector().project([*existing_events, *candidate_events])
        worker_summary = projected.workers.get(worker_id)
        if worker_summary is None:
            raise ValueError("worker handoff did not project worker summary")
        for event in candidate_events:
            self.event_store.append(event)

        return {
            "status": worker_summary["status"],
            "delegation_id": delegation_id,
            "decision_id": decision_id,
            "worker_id": worker_id,
            "result_ref": artifact_ref.to_dict(),
            "worker_summary": deepcopy(worker_summary),
            "basis_event_ids": [event.event_id for event in candidate_events],
            "private_append_required": False,
        }


    def _validate_worker_handoff_intent(self, intent: object) -> dict[str, Any]:
        if not isinstance(intent, dict) or not intent:
            raise IsotopeError(
                "delegation intent must be a non-empty dict",
                code="worker_handoff_invalid_intent",
                category="validation",
                retryable=False,
                http_status=400,
                details={"field": "delegation_intent"},
            )
        if "decision" in intent or "grants" in intent or "effective_grants" in intent:
            raise IsotopeError(
                "delegation intent cannot include forged decision or grants",
                code="worker_handoff_forged_grants",
                category="policy",
                retryable=False,
                http_status=403,
                details={"field": "delegation_intent"},
            )
        parent_agent_id = intent.get("parent_agent_id")
        requested_worker_role = intent.get("requested_worker_role")
        requested_capabilities = intent.get("requested_capabilities")
        self._validate_non_empty_string("parent_agent_id", parent_agent_id)
        self._validate_non_empty_string("requested_worker_role", requested_worker_role)
        if requested_worker_role != "worker":
            raise ValueError("requested_worker_role must be worker")
        if not isinstance(requested_capabilities, dict):
            raise ValueError("delegation intent requested_capabilities must be a dict")
        requested_tools = requested_capabilities.get("tools", [])
        if not isinstance(requested_tools, list):
            raise ValueError("delegation intent tools must be a list")
        requested_workspace = requested_capabilities.get("workspace", {})
        if not isinstance(requested_workspace, dict):
            raise ValueError("delegation intent workspace must be a dict")
        requested_budget = requested_capabilities.get("budget", {})
        if not isinstance(requested_budget, dict):
            raise ValueError("delegation intent budget must be a dict")
        try:
            budget_seconds = int(requested_budget.get("seconds", 30))
        except (TypeError, ValueError) as exc:
            raise ValueError("delegation intent budget.seconds must be int-like") from exc
        if budget_seconds < 0:
            raise ValueError("delegation intent budget.seconds must be non-negative")
        return {
            "parent_agent_id": parent_agent_id,
            "requested_worker_role": requested_worker_role,
            "requested_capabilities": {
                "tools": list(requested_tools),
                "workspace": dict(requested_workspace),
                "budget": {"seconds": budget_seconds},
            },
        }

    def _derive_worker_handoff_grants(self, requested_capabilities: dict[str, Any]) -> tuple[dict[str, Any], str, list[str]]:
        requested_tools = requested_capabilities["tools"]
        if "write_artifact_tool" not in requested_tools:
            return (
                {"tools": [], "workspace": {"mode": "none"}, "budget": {"seconds": 0}},
                "denied",
                ["tool_not_requested"],
            )

        requested_workspace = requested_capabilities["workspace"]
        requested_budget = requested_capabilities["budget"]
        budget_seconds = int(requested_budget["seconds"])
        grants = {
            "tools": ["write_artifact_tool"],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": min(budget_seconds, 30)},
        }
        requested_matches = (
            requested_tools == grants["tools"]
            and requested_workspace.get("mode", "shared_ro") == "shared_ro"
            and budget_seconds <= 30
        )
        return grants, "approved" if requested_matches else "modified", [] if requested_matches else ["capabilities_reduced"]

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
