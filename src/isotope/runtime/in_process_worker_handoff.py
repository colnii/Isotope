"""Worker handoff helpers for the in-process runtime."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..platform.errors import IsotopeError, IsotopePermissionError
from ..platform.ids import new_id
from ..platform.schemas.refs import ResourceRef
from ..platform.state.projector import RunProjector


class InProcessWorkerHandoffMixin:
    """Validate and append worker delegation handoff events."""

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
