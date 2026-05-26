"""Approval helpers for the in-process runtime facade."""

from __future__ import annotations

from copy import deepcopy
import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from ...platform.schemas.actions import ActionProposal, PolicyDecision


class InProcessApprovalMixin:
    """Resolve and recover pending approval state."""

    def resolve_approval(self, approval_id: str, resolution: dict[str, Any]) -> dict[str, Any]:
        self._validate_non_empty_string("approval_id", approval_id)
        body = self._validate_approval_resolution_body(resolution)

        if approval_id in self._resolved_approvals:
            raise ValueError("approval already resolved")

        pending = self._pending_approvals.get(approval_id)
        if pending is None:
            pending = self._recover_pending_approval_context(approval_id)

        run_id = pending["run_id"]
        approval_event = self._find_approval_requested_event(run_id, approval_id)
        if approval_event is None:
            raise ValueError("unknown approval")
        approval_payload = approval_event.payload

        self._append(
            run_id,
            "approval.resolved",
            {
                "approval_id": approval_id,
                "run_id": run_id,
                "proposal_id": approval_payload["proposal_id"],
                "decision_id": approval_payload["decision_id"],
                "resolution": body["resolution"],
                "reason": body["reason"],
                "resolver": body["resolver"],
                "basis_event_id": approval_event.event_id,
            },
        )

        if body["resolution"] == "denied":
            result = {
                "status": "denied",
                "run_state": self.get_run_state(run_id),
            }
            self._resolved_approvals[approval_id] = result
            return result

        original_decision: PolicyDecision = pending["decision"]
        proposal = pending["proposal"]
        complete_run = pending.get("complete_run", True)
        if not isinstance(complete_run, bool):
            raise ValueError("complete_run must be a bool")
        executable_decision = PolicyDecision(
            decision_id=original_decision.decision_id,
            proposal_id=original_decision.proposal_id,
            outcome="approved",
            grants=original_decision.grants,
            reason_codes=list(original_decision.reason_codes),
            policy_profile_id=original_decision.policy_profile_id,
            policy_version=original_decision.policy_version,
        )

        try:
            execution = self.executor.execute(executable_decision, proposal)
        except Exception as exc:
            execution_id = self._latest_failed_execution_id(
                run_id,
                proposal_id=proposal.proposal_id,
                decision_id=executable_decision.decision_id,
            )
            if not execution_id:
                raise RuntimeError("executor failed without action.failed event") from exc
            result = {
                "status": "failed",
                "execution": None,
                "execution_id": execution_id,
                "run_state": self.get_run_state(run_id),
            }
            self._resolved_approvals[approval_id] = result
            return result

        if complete_run:
            self._append(run_id, "run.completed", {"status": "completed"})
        state = self.get_run_state(run_id)
        result = {
            "status": state.status,
            "tool_execution_status": "completed",
            "run_state": state,
            "execution_id": execution.execution_id,
        }
        artifact_ref = self._completed_artifact_ref(run_id, execution.execution_id)
        if artifact_ref is not None:
            result["artifact_ref"] = artifact_ref
        self._resolved_approvals[approval_id] = result
        return result

    def _recover_pending_approval_context(self, approval_id: str) -> dict[str, Any]:
        approval_event = self._find_approval_requested_event_by_id(approval_id)
        if approval_event is None:
            raise ValueError("unknown approval")
        run_id = approval_event.payload.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            raise ValueError("unknown approval")

        state = self.get_run_state(run_id)
        approval_summary = state.approvals.get(approval_id)
        if approval_summary is None:
            raise ValueError("unknown approval")
        if approval_summary.get("status") != "pending":
            raise ValueError("approval already resolved")

        context = approval_event.payload.get("resolution_context")
        if not isinstance(context, dict):
            raise ValueError("approval resolution context unavailable")
        proposal = self._proposal_from_approval_context(context.get("proposal"), run_id)
        decision = self._decision_from_approval_context(context.get("decision"), proposal.proposal_id)
        complete_run = context.get("complete_run", True)
        if not isinstance(complete_run, bool):
            raise ValueError("approval completion context unavailable")
        return {
            "run_id": run_id,
            "proposal": proposal,
            "decision": decision,
            "complete_run": complete_run,
        }

    def _proposal_from_approval_context(self, raw: object, run_id: str) -> ActionProposal:
        if not isinstance(raw, dict):
            raise ValueError("approval proposal context unavailable")
        proposal = ActionProposal(
            proposal_id=self._context_string(raw, "proposal_id"),
            run_id=self._context_string(raw, "run_id"),
            agent_id=self._context_string(raw, "agent_id"),
            thread_id=self._context_string(raw, "thread_id"),
            action_type=self._context_string(raw, "action_type"),
            payload=self._load_pending_approval_payload(run_id, self._context_string(raw, "payload_ref")),
            requested_capabilities=deepcopy(self._context_dict(raw, "requested_capabilities")),
            registry_id=self._context_string(raw, "registry_id"),
            registry_version=self._context_string(raw, "registry_version"),
        )
        if proposal.run_id != run_id:
            raise ValueError("approval proposal context run_id mismatch")
        return proposal

    def _decision_from_approval_context(self, raw: object, proposal_id: str) -> PolicyDecision:
        if not isinstance(raw, dict):
            raise ValueError("approval decision context unavailable")
        decision = PolicyDecision(
            decision_id=self._context_string(raw, "decision_id"),
            proposal_id=self._context_string(raw, "proposal_id"),
            outcome=self._context_string(raw, "outcome"),
            grants=deepcopy(self._context_dict(raw, "grants")),
            reason_codes=list(self._context_list(raw, "reason_codes")),
            policy_profile_id=self._context_string(raw, "policy_profile_id"),
            policy_version=self._context_string(raw, "policy_version"),
        )
        if decision.proposal_id != proposal_id:
            raise ValueError("approval decision context proposal_id mismatch")
        return decision

    def _context_string(self, raw: dict[str, Any], field_name: str) -> str:
        value = raw.get(field_name)
        if not isinstance(value, str) or not value:
            raise ValueError(f"approval context {field_name} unavailable")
        return value

    def _context_dict(self, raw: dict[str, Any], field_name: str) -> dict[str, Any]:
        value = raw.get(field_name)
        if not isinstance(value, dict):
            raise ValueError(f"approval context {field_name} unavailable")
        return value

    def _context_list(self, raw: dict[str, Any], field_name: str) -> list[Any]:
        value = raw.get(field_name)
        if not isinstance(value, list):
            raise ValueError(f"approval context {field_name} unavailable")
        return value

    def _pending_approval_payload_path(self, run_id: str, payload_ref: str) -> Path:
        self._validate_non_empty_string("run_id", run_id)
        self._validate_non_empty_string("payload_ref", payload_ref)
        return self.root / "runs" / run_id / "approval_payloads" / f"{payload_ref}.json"

    def _store_pending_approval_payload(
        self,
        run_id: str,
        approval_id: str,
        payload: dict[str, Any],
    ) -> str:
        if not isinstance(payload, dict):
            raise ValueError("approval payload must be a dict")
        payload_ref = f"{approval_id}_payload"
        path = self._pending_approval_payload_path(run_id, payload_ref)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"payload": payload}, sort_keys=True), encoding="utf-8")
        return payload_ref

    def _load_pending_approval_payload(self, run_id: str, payload_ref: str) -> dict[str, Any]:
        path = self._pending_approval_payload_path(run_id, payload_ref)
        if not path.exists():
            raise ValueError("approval payload context unavailable")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except JSONDecodeError as exc:
            raise ValueError("malformed approval payload context") from exc
        if not isinstance(data, dict) or not isinstance(data.get("payload"), dict):
            raise ValueError("malformed approval payload context")
        return deepcopy(data["payload"])


    def get_pending_approvals(self, run_id: str) -> list[dict[str, Any]]:
        state = self._get_approval_read_state(run_id)
        return [
            deepcopy(approval)
            for approval in state.approvals.values()
            if approval.get("status") == "pending"
        ]

    def get_approval(self, run_id: str, approval_id: str) -> dict[str, Any]:
        self._validate_non_empty_string("approval_id", approval_id)
        state = self._get_approval_read_state(run_id)
        approval = state.approvals.get(approval_id)
        if approval is None:
            raise ValueError("unknown approval")
        return deepcopy(approval)


    def _validate_approval_resolution_body(self, body: object) -> dict[str, str]:
        if not isinstance(body, dict):
            raise ValueError("resolution body must be a dict")
        resolution = body.get("resolution")
        if resolution not in {"approved", "denied"}:
            raise ValueError("resolution must be approved or denied")
        reason = body.get("reason")
        if not isinstance(reason, str) or not reason:
            raise ValueError("reason must be a non-empty string")
        resolver = body.get("resolver")
        if not isinstance(resolver, str) or not resolver:
            raise ValueError("resolver must be a non-empty string")
        return {
            "resolution": resolution,
            "reason": reason,
            "resolver": resolver,
        }
