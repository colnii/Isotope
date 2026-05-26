"""RunProjector event lifecycle validation helpers."""

from __future__ import annotations

from typing import Any

from ...events.events import CanonicalEvent


class RunProjectorLifecycleValidationMixin:
    """Validate cross-event ordering and lifecycle transitions."""

    def _validate_lifecycle(self, event: CanonicalEvent) -> None:
        payload = event.payload
        self._validate_event_payload(event)
        if self._run_completed and event.event_type in {
            "action.decided",
            "action.started",
            "action.failed",
            "action.completed",
            "action.cancel_requested",
            "action.cancelled",
            "artifact.created",
            "memory.record_created",
            "memory.record_superseded",
            "workspace.bound",
            "workspace.lease_created",
            "workspace.released",
            "workspace.artifact_captured",
        }:
            raise ValueError("event after run.completed")

        if event.event_type == "action.proposed":
            proposal_id = payload.get("proposal_id")
            action_type = payload.get("action_type")
            if isinstance(proposal_id, str) and isinstance(action_type, str):
                self._proposal_action_types[proposal_id] = action_type
                registry_basis = self._registry_basis_from_payload(payload)
                self._proposal_registry_basis[proposal_id] = registry_basis
                requested_summary = payload.get("requested_action_summary")
                if isinstance(requested_summary, dict):
                    self._proposal_summaries[proposal_id] = dict(requested_summary)
                agent_id = payload.get("agent_id")
                if isinstance(agent_id, str) and agent_id:
                    self._proposal_agents[proposal_id] = agent_id
        elif event.event_type == "action.decided":
            proposal_id = str(payload["proposal_id"])
            self._proposal_outcomes[proposal_id] = str(payload["outcome"])
            reason_codes = payload.get("reason_codes", [])
            self._proposal_reason_codes[proposal_id] = list(reason_codes) if isinstance(reason_codes, list) else []
            grants = payload.get("grants")
            if isinstance(grants, dict):
                self._proposal_grants[proposal_id] = dict(grants)
            self._proposal_policy_basis[proposal_id] = self._policy_basis_from_payload(payload)
        elif event.event_type == "action.started":
            proposal_id = str(payload["proposal_id"])
            outcome = self._proposal_outcomes.get(proposal_id)
            if outcome == "denied":
                raise ValueError("action.started after denied decision")
            if outcome == "pending_user_approval":
                raise ValueError("action.started after pending approval")
            if outcome not in self.EXECUTABLE_DECISION_OUTCOMES:
                raise ValueError("action.started before approved decision")
            agent_id = self._proposal_agents.get(proposal_id, "")
            if agent_id in self._worker_agent_ids and proposal_id not in self._proposal_grants:
                raise ValueError("worker action requires policy grants")
            self._execution_statuses[str(payload["execution_id"])] = "running"
            self._execution_action_types[str(payload["execution_id"])] = self._proposal_action_types.get(proposal_id, "")
            self._execution_proposals[str(payload["execution_id"])] = proposal_id
            self._proposal_execution_ids[proposal_id] = str(payload["execution_id"])
            self._proposal_start_event_ids[proposal_id] = event.event_id
        elif event.event_type == "delegation.proposed":
            self._delegation_proposals[str(payload["delegation_id"])] = dict(payload)
        elif event.event_type == "delegation.decided":
            delegation_id = str(payload["delegation_id"])
            if delegation_id not in self._delegation_proposals:
                raise ValueError("delegation.decided requires delegation.proposed")
            self._delegation_decisions[delegation_id] = dict(payload)
        elif event.event_type == "worker.created":
            delegation_id = str(payload["delegation_id"])
            if delegation_id not in self._delegation_proposals:
                raise ValueError("worker.created requires approved delegation via delegation.proposed")
            decision = self._delegation_decisions.get(delegation_id)
            if decision is None:
                raise ValueError("worker.created requires delegation.decided")
            outcome = decision.get("outcome")
            if outcome == "denied":
                raise ValueError("denied delegation cannot create worker")
            if outcome not in self.EXECUTABLE_DECISION_OUTCOMES:
                raise ValueError("worker.created requires approved delegation")
            if payload.get("decision_id") != decision.get("decision_id"):
                raise ValueError("worker.created decision_id must match delegation.decided")
            worker_id = str(payload["worker_id"])
            self._workers[worker_id] = dict(payload)
            self._worker_agent_ids.add(str(payload["agent_id"]))
        elif event.event_type in {"worker.started", "worker.completed", "worker.failed", "worker.cancelled"}:
            self._validate_worker_lifecycle_transition(payload, event.event_type)
        elif event.event_type == "worker.result_handed_off":
            self._validate_worker_lifecycle_transition(payload, event.event_type)
        elif event.event_type == "workspace.bound":
            self._validate_workspace_bound_lifecycle(payload, event)
        elif event.event_type == "workspace.lease_created":
            self._validate_workspace_lease_created_lifecycle(payload, event)
        elif event.event_type == "workspace.released":
            self._validate_workspace_released_lifecycle(payload, event)
        elif event.event_type == "workspace.artifact_captured":
            self._validate_workspace_artifact_captured_lifecycle(payload, event)
        elif event.event_type == "artifact.created":
            ref = payload["artifact"]["ref"]
            self._artifact_ref_event_ids[self._stable_json(ref)] = event.event_id
        elif event.event_type == "action.completed":
            execution_id = str(payload["execution_id"])
            status = self._execution_statuses.get(execution_id)
            if status is None:
                raise ValueError("action.completed before action.started")
            if status == "failed":
                raise ValueError("terminal execution already failed")
            if status == "cancelled":
                raise ValueError("action.completed after action.cancelled")
            if status == "superseded":
                raise ValueError("action.completed after action.superseded")
            self._execution_statuses[execution_id] = "completed"
        elif event.event_type == "action.failed":
            execution_id = str(payload["execution_id"])
            status = self._execution_statuses.get(execution_id)
            if status == "completed":
                raise ValueError("terminal execution already completed")
            self._execution_statuses[execution_id] = "failed"
        elif event.event_type == "action.retry_requested":
            original_execution_id = str(payload["original_execution_id"])
            original_status = self._execution_statuses.get(original_execution_id)
            if original_status == "completed":
                if payload.get("explicit_rerun") is not True:
                    raise ValueError("action.retry_requested completed execution requires explicit rerun")
            elif original_status != "failed":
                raise ValueError("action.retry_requested requires failed execution")
            if self._execution_proposals.get(original_execution_id) != payload["original_proposal_id"]:
                raise ValueError("action.retry_requested original_proposal_id must match original execution")
            retry_request = dict(payload)
            retry_request["_request_event_id"] = event.event_id
            self._retry_requests[str(payload["retry_id"])] = retry_request
        elif event.event_type == "action.retry_created":
            retry_id = str(payload["retry_id"])
            retry_request = self._retry_requests.get(retry_id)
            if retry_request is None:
                raise ValueError("action.retry_created requires action.retry_requested")
            if payload["original_proposal_id"] != retry_request["original_proposal_id"]:
                raise ValueError("action.retry_created original_proposal_id must match retry request")
            if payload["basis_event_id"] != retry_request["_request_event_id"]:
                raise ValueError("action.retry_created basis_event_id must match action.retry_requested")
            if payload["new_proposal_id"] == payload["original_proposal_id"]:
                raise ValueError("action.retry_created new_proposal_id must differ from original_proposal_id")
        elif event.event_type == "action.cancel_requested":
            execution_id = payload.get("execution_id")
            if isinstance(execution_id, str) and execution_id:
                status = self._execution_statuses.get(execution_id)
                if status in {"completed", "failed", "cancelled", "superseded"}:
                    raise ValueError("action.cancel_requested after terminal action state")
                if status != "running":
                    raise ValueError("action.cancel_requested requires running action")
                if self._execution_proposals.get(execution_id) != payload["proposal_id"]:
                    raise ValueError("action.cancel_requested proposal_id must match execution proposal")
            else:
                proposal_id = str(payload["proposal_id"])
                if self._proposal_outcomes.get(proposal_id) != "pending_user_approval":
                    raise ValueError("action.cancel_requested requires running action or pending approval")
            cancel_request = dict(payload)
            cancel_request["_request_event_id"] = event.event_id
            self._cancel_requests[str(payload["cancel_id"])] = cancel_request
        elif event.event_type == "action.cancelled":
            cancel_request = self._cancel_requests.get(str(payload["cancel_id"]))
            if cancel_request is None:
                raise ValueError("action.cancelled requires action.cancel_requested")
            if payload["basis_event_id"] != cancel_request["_request_event_id"]:
                raise ValueError("action.cancelled basis_event_id must match action.cancel_requested")
            if payload["proposal_id"] != cancel_request["proposal_id"]:
                raise ValueError("action.cancelled proposal_id must match action.cancel_requested")
            if payload["execution_id"] != cancel_request["execution_id"]:
                raise ValueError("action.cancelled execution_id must match action.cancel_requested")
            execution_id = str(payload["execution_id"])
            if self._execution_statuses.get(execution_id) != "running":
                raise ValueError("action.cancelled requires running action")
            self._execution_statuses[execution_id] = "cancelled"
        elif event.event_type == "action.superseded":
            old_proposal_id = str(payload["old_proposal_id"])
            if payload["new_proposal_id"] == payload["old_proposal_id"]:
                raise ValueError("action.superseded new_proposal_id must differ from old_proposal_id")
            if payload["basis_event_id"] != self._proposal_start_event_ids.get(old_proposal_id):
                raise ValueError("action.superseded basis_event_id must match old action start event")
            execution_id = self._proposal_execution_ids.get(old_proposal_id)
            if execution_id is None:
                raise ValueError("action.superseded requires started action")
            execution_status = self._execution_statuses.get(execution_id)
            if execution_status not in {"running", "completed"}:
                raise ValueError("action.superseded requires running action")
            if execution_status == "running":
                self._execution_statuses[execution_id] = "superseded"
        elif event.event_type == "approval.requested":
            self._approval_proposals[str(payload["approval_id"])] = str(payload["proposal_id"])
        elif event.event_type == "approval.resolved":
            approval_id = str(payload["approval_id"])
            proposal_id = str(payload["proposal_id"])
            if approval_id in self._approval_resolutions:
                raise ValueError("approval.resolved duplicate approval_id")
            if self._approval_proposals.get(approval_id) != proposal_id:
                raise ValueError("approval.resolved requires pending approval")
            if self._proposal_outcomes.get(proposal_id) != "pending_user_approval":
                raise ValueError("approval.resolved requires pending approval")
            resolution = str(payload["resolution"])
            if resolution == "approved":
                self._proposal_outcomes[proposal_id] = "approved"
            elif resolution == "denied":
                self._proposal_outcomes[proposal_id] = "denied"
            self._approval_resolutions.add(approval_id)
        elif event.event_type == "memory.record_created":
            self._validate_memory_record_lifecycle(payload)
            self._memory_record_ids.add(str(payload["record_id"]))
        elif event.event_type == "memory.record_superseded":
            self._validate_memory_record_superseded_lifecycle(payload)
        elif event.event_type == "run.completed":
            self._validate_run_completed()
            self._run_completed = True

    def _validate_worker_lifecycle_transition(self, payload: dict[str, Any], event_type: str) -> None:
        worker_id = str(payload["worker_id"])
        worker = self._workers.get(worker_id)
        if worker is None:
            raise ValueError(f"{event_type} requires worker.created")
        if payload.get("delegation_id") != worker.get("delegation_id"):
            raise ValueError(f"{event_type} delegation_id must match worker.created")

    def _validate_run_completed(self) -> None:
        statuses = set(self._execution_statuses.values())
        if "failed" in statuses:
            raise ValueError("run.completed after failed execution")
        if "running" in statuses:
            raise ValueError("run.completed while executions are still running")
        if "pending_user_approval" in set(self._proposal_outcomes.values()):
            raise ValueError("run.completed while approval is pending")
        if "completed" not in statuses:
            raise ValueError("run.completed requires a completed execution")
