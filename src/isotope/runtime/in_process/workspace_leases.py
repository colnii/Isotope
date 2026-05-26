"""Workspace lease and binding helpers for the in-process runtime."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ...platform.schemas.actions import PolicyDecision
from ...platform.schemas.refs import ResourceRef


class InProcessWorkspaceLeaseMixin:
    """Manage runtime workspace bindings and lease lifecycle."""

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
