"""RunProjector event application helpers."""

from __future__ import annotations

import json
from typing import Any

from ..events.events import CanonicalEvent
from .projector_state import RunState, _ObservationDict


class RunProjectorHandlersMixin:
    """Apply validated canonical events to RunState."""

    def _projected_action_basis(self, proposal_id: str) -> dict[str, Any]:
        projected: dict[str, Any] = {}
        registry_basis = self._proposal_registry_basis.get(proposal_id)
        if registry_basis is not None:
            projected.update(registry_basis)
            projected["registry_basis"] = dict(registry_basis)
        policy_basis = self._proposal_policy_basis.get(proposal_id)
        if policy_basis is not None:
            projected.update(policy_basis)
            projected["policy_basis"] = dict(policy_basis)
        reason_codes = self._proposal_reason_codes.get(proposal_id)
        if reason_codes is not None:
            projected["reason_codes"] = list(reason_codes)
        requested_summary = self._proposal_summaries.get(proposal_id)
        if requested_summary is not None:
            projected["requested_action_summary"] = dict(requested_summary)
        return projected

    def apply(self, state: RunState, event: CanonicalEvent) -> None:
        state.last_event_id = event.event_id
        if not state.run_id:
            state.run_id = event.run_id

        payload = event.payload
        if event.event_type == "run.created":
            state.run_id = str(payload.get("run_id", event.run_id))
            state.session_id = str(payload.get("session_id", ""))
            state.goal = str(payload.get("goal", ""))
            state.created_event_id = event.event_id
            state.status = "running"
        elif event.event_type == "agent.created":
            agent_id = str(payload["agent_id"])
            state.current_agent = agent_id
            state.agents[agent_id] = {
                "agent_id": agent_id,
                "run_id": payload.get("run_id", event.run_id),
                "role": payload.get("role", "supervisor"),
                "status": payload.get("status", "created"),
                "created_event_id": event.event_id,
                "last_event_id": event.event_id,
            }
        elif event.event_type == "action.started":
            execution_id = str(payload["execution_id"])
            proposal_id = str(payload.get("proposal_id", ""))
            state.actions[execution_id] = {
                "execution_id": execution_id,
                "proposal_id": proposal_id,
                "decision_id": payload.get("decision_id"),
                "agent_id": self._proposal_agents.get(proposal_id),
                "status": "running",
                **self._projected_action_basis(proposal_id),
            }
        elif event.event_type == "delegation.proposed":
            self._apply_delegation_proposed(state, payload, event)
        elif event.event_type == "delegation.decided":
            self._apply_delegation_decided(state, payload, event)
        elif event.event_type == "worker.created":
            self._apply_worker_created(state, payload, event)
        elif event.event_type in {"worker.started", "worker.completed", "worker.failed", "worker.cancelled"}:
            self._apply_worker_status(state, payload, event)
        elif event.event_type == "worker.result_handed_off":
            self._apply_worker_result_handoff(state, payload, event)
        elif event.event_type == "workspace.bound":
            self._apply_workspace_bound(state, payload, event)
        elif event.event_type == "workspace.lease_created":
            self._apply_workspace_lease_created(state, payload, event)
        elif event.event_type == "workspace.released":
            self._apply_workspace_released(state, payload, event)
        elif event.event_type == "workspace.artifact_captured":
            self._apply_workspace_artifact_captured(state, payload, event)
        elif event.event_type == "action.decided":
            outcome = str(payload.get("outcome", ""))
            if outcome in {"denied", "pending_user_approval"}:
                proposal_id = str(payload["proposal_id"])
                state.actions[proposal_id] = {
                    "proposal_id": proposal_id,
                    "decision_id": payload.get("decision_id"),
                    "status": outcome,
                    **self._projected_action_basis(proposal_id),
                }
                if outcome == "pending_user_approval":
                    state.status = "pending_user_approval"
        elif event.event_type == "approval.requested":
            proposal_id = str(payload["proposal_id"])
            action = state.actions.setdefault(proposal_id, {"proposal_id": proposal_id})
            action.update(self._projected_action_basis(proposal_id))
            action["decision_id"] = payload.get("decision_id")
            action["approval_id"] = payload.get("approval_id")
            action["status"] = "pending_user_approval"
            approval_id = str(payload["approval_id"])
            state.approvals[approval_id] = {
                "approval_id": approval_id,
                "run_id": payload.get("run_id", event.run_id),
                "proposal_id": proposal_id,
                "decision_id": payload.get("decision_id"),
                "status": "pending",
                "reason_codes": list(self._proposal_reason_codes.get(proposal_id, [])),
                "requested_action_summary": dict(
                    self._proposal_summaries.get(
                        proposal_id,
                        {"action_type": payload.get("action_type")},
                    )
                ),
            }
            state.status = "pending_user_approval"
        elif event.event_type == "approval.resolved":
            proposal_id = str(payload["proposal_id"])
            action = state.actions.setdefault(proposal_id, {"proposal_id": proposal_id})
            action.update(self._projected_action_basis(proposal_id))
            action["decision_id"] = payload.get("decision_id")
            approval_id = str(payload["approval_id"])
            action["approval_id"] = approval_id
            action["approval_resolution"] = payload.get("resolution")
            action["approval_resolved_event_id"] = event.event_id
            action["approval_reason"] = payload.get("reason")
            resolution = payload.get("resolution")
            action["status"] = "approved" if resolution == "approved" else "denied"
            approval = state.approvals.setdefault(
                approval_id,
                {
                    "approval_id": approval_id,
                    "run_id": payload.get("run_id", event.run_id),
                    "proposal_id": proposal_id,
                    "decision_id": payload.get("decision_id"),
                },
            )
            approval.update(
                {
                    "status": resolution,
                    "resolution": resolution,
                    "reason": payload.get("reason"),
                    "resolver": payload.get("resolver"),
                    "resolved_event_id": event.event_id,
                    "basis_event_id": payload.get("basis_event_id"),
                }
            )
            if resolution == "approved":
                state.status = "running"
            else:
                state.status = "denied"
        elif event.event_type == "artifact.created":
            artifact = dict(payload["artifact"])
            projected_artifact = {
                "ref": dict(artifact["ref"]),
                "artifact_type": artifact["artifact_type"],
                "summary": artifact["summary"],
                "provenance": dict(artifact["provenance"]),
            }
            if artifact.get("basis_refs"):
                projected_artifact["basis_refs"] = [dict(ref) for ref in artifact["basis_refs"]]
            if artifact.get("source_refs"):
                projected_artifact["source_refs"] = [dict(ref) for ref in artifact["source_refs"]]
            state.artifacts.append(projected_artifact)
        elif event.event_type == "action.completed":
            execution_id = str(payload["execution_id"])
            action = state.actions.setdefault(execution_id, {"execution_id": execution_id})
            action["status"] = payload.get("status", "completed")
            action["artifact_refs"] = [dict(ref) for ref in payload.get("artifact_refs", [])]
            terminal_backend = payload.get("terminal_backend")
            if isinstance(terminal_backend, dict):
                action["terminal_backend"] = dict(terminal_backend)
            codex_task = payload.get("codex_task")
            if isinstance(codex_task, dict):
                action["codex_task"] = dict(codex_task)
        elif event.event_type == "action.failed":
            execution_id = str(payload["execution_id"])
            action = state.actions.setdefault(execution_id, {"execution_id": execution_id})
            action["proposal_id"] = payload.get("proposal_id")
            action["decision_id"] = payload.get("decision_id")
            action.update(self._projected_action_basis(str(payload.get("proposal_id", ""))))
            action["status"] = payload.get("status", "failed")
            state.status = "failed"
        elif event.event_type == "action.retry_requested":
            retry_id = str(payload["retry_id"])
            state.action_retries[retry_id] = {
                "retry_id": retry_id,
                "original_proposal_id": payload["original_proposal_id"],
                "original_execution_id": payload["original_execution_id"],
                "status": "requested",
                "basis_event_id": event.event_id,
            }
        elif event.event_type == "action.retry_created":
            retry_id = str(payload["retry_id"])
            retry = state.action_retries.setdefault(retry_id, {"retry_id": retry_id})
            retry.update(
                {
                    "original_proposal_id": payload["original_proposal_id"],
                    "original_execution_id": retry.get("original_execution_id"),
                    "new_proposal_id": payload["new_proposal_id"],
                    "status": "created",
                    "basis_event_id": payload["basis_event_id"],
                }
            )
            if payload.get("new_execution_id") is not None:
                retry["new_execution_id"] = payload.get("new_execution_id")
        elif event.event_type == "action.cancel_requested":
            cancel_id = str(payload["cancel_id"])
            state.action_cancellations[cancel_id] = {
                "cancel_id": cancel_id,
                "proposal_id": payload["proposal_id"],
                "execution_id": payload.get("execution_id"),
                "status": "requested",
                "basis_event_id": event.event_id,
            }
        elif event.event_type == "action.cancelled":
            cancel_id = str(payload["cancel_id"])
            cancellation = state.action_cancellations.setdefault(cancel_id, {"cancel_id": cancel_id})
            cancellation.update(
                {
                    "proposal_id": payload["proposal_id"],
                    "execution_id": payload["execution_id"],
                    "status": "cancelled",
                    "basis_event_id": payload["basis_event_id"],
                }
            )
            execution_id = str(payload["execution_id"])
            action = state.actions.setdefault(execution_id, {"execution_id": execution_id})
            action["status"] = "cancelled"
        elif event.event_type == "action.superseded":
            supersession_id = str(payload["supersession_id"])
            state.action_supersessions[supersession_id] = {
                "supersession_id": supersession_id,
                "old_proposal_id": payload["old_proposal_id"],
                "new_proposal_id": payload["new_proposal_id"],
                "status": "created",
                "basis_event_id": payload["basis_event_id"],
            }
            if payload.get("old_execution_id") is not None:
                state.action_supersessions[supersession_id]["old_execution_id"] = payload.get("old_execution_id")
            if payload.get("new_execution_id") is not None:
                state.action_supersessions[supersession_id]["new_execution_id"] = payload.get("new_execution_id")
            execution_id = self._proposal_execution_ids.get(str(payload["old_proposal_id"]))
            if execution_id is not None:
                action = state.actions.setdefault(execution_id, {"execution_id": execution_id})
                if action.get("status") != "completed":
                    action["status"] = "superseded"
        elif event.event_type == "memory.record_created":
            state.memory_records.append(
                {
                    "record_id": payload["record_id"],
                    "execution_id": payload["execution_id"],
                    "summary": payload["summary"],
                    "source_refs": list(payload["source_refs"]),
                    "provenance": dict(payload["provenance"]),
                    "basis_event_id": payload["basis_event_id"],
                    "quality": payload.get("quality"),
                }
            )
        elif event.event_type == "memory.record_superseded":
            old_record_id = str(payload["old_record_id"])
            for record in state.memory_records:
                if record["record_id"] == old_record_id:
                    record["status"] = "superseded"
                    record["superseded_by"] = payload["new_record_id"]
                    record["superseded_event_id"] = event.event_id
                    record["superseded_reason"] = payload["reason"]
                    break
        elif event.event_type == "snapshot.imported":
            self._apply_snapshot_imported(state, payload)
        elif event.event_type == "run.completed":
            state.completed_event_id = event.event_id
            state.status = str(payload.get("status", "completed"))

    def _apply_delegation_proposed(self, state: RunState, payload: dict[str, Any], event: CanonicalEvent) -> None:
        delegation_id = str(payload["delegation_id"])
        state.delegations[delegation_id] = {
            "delegation_id": delegation_id,
            "run_id": payload.get("run_id", event.run_id),
            "parent_agent_id": payload["parent_agent_id"],
            "requested_worker_role": payload["requested_worker_role"],
            "requested_capabilities": dict(payload["requested_capabilities"]),
            "status": "proposed",
            "proposed_event_id": event.event_id,
            "last_event_id": event.event_id,
        }

    def _apply_delegation_decided(self, state: RunState, payload: dict[str, Any], event: CanonicalEvent) -> None:
        delegation_id = str(payload["delegation_id"])
        proposal = self._delegation_proposals[delegation_id]
        policy_basis = payload.get("policy_basis")
        if policy_basis is None:
            policy_basis = {
                key: payload[key]
                for key in ("policy_profile_id", "policy_version")
                if key in payload
            }
        delegation = state.delegations.setdefault(
            delegation_id,
            {
                "delegation_id": delegation_id,
                "run_id": proposal.get("run_id", event.run_id),
                "parent_agent_id": proposal["parent_agent_id"],
                "requested_worker_role": proposal["requested_worker_role"],
                "requested_capabilities": dict(proposal["requested_capabilities"]),
            },
        )
        delegation.update(
            {
                "decision_id": payload["decision_id"],
                "outcome": payload["outcome"],
                "status": payload["outcome"],
                "reason_codes": list(payload.get("reason_codes", [])),
                "grants": dict(payload["grants"]),
                "policy_basis": dict(policy_basis),
                "decided_event_id": event.event_id,
                "last_event_id": event.event_id,
            }
        )

    def _apply_worker_created(self, state: RunState, payload: dict[str, Any], event: CanonicalEvent) -> None:
        worker_id = str(payload["worker_id"])
        delegation_id = str(payload["delegation_id"])
        proposal = self._delegation_proposals[delegation_id]
        decision = self._delegation_decisions[delegation_id]
        grants = dict(decision["grants"])
        workspace = dict(grants.get("workspace", payload["workspace"]))
        worker = {
            "worker_id": worker_id,
            "agent_id": payload["agent_id"],
            "run_id": payload.get("run_id", event.run_id),
            "parent_agent_id": payload["parent_agent_id"],
            "delegation_id": delegation_id,
            "decision_id": payload["decision_id"],
            "role": payload["role"],
            "status": "created",
            "requested_capabilities": dict(proposal["requested_capabilities"]),
            "grants": grants,
            "workspace": workspace,
            "result_refs": [],
            "created_event_id": event.event_id,
            "last_event_id": event.event_id,
        }
        state.workers[worker_id] = worker
        delegation = state.delegations.setdefault(delegation_id, {"delegation_id": delegation_id})
        delegation["worker_id"] = worker_id
        delegation["worker_agent_id"] = payload["agent_id"]
        delegation["worker_created_event_id"] = event.event_id
        delegation["last_event_id"] = event.event_id
        agent_id = str(payload["agent_id"])
        state.agents[agent_id] = {
            "agent_id": agent_id,
            "run_id": payload.get("run_id", event.run_id),
            "role": payload["role"],
            "status": "created",
            "parent_agent_id": payload["parent_agent_id"],
            "delegation_id": delegation_id,
            "worker_id": worker_id,
            "created_event_id": event.event_id,
            "last_event_id": event.event_id,
        }

    def _apply_worker_status(self, state: RunState, payload: dict[str, Any], event: CanonicalEvent) -> None:
        worker_id = str(payload["worker_id"])
        worker = state.workers.setdefault(worker_id, {"worker_id": worker_id})
        status = str(payload["status"])
        worker["status"] = status
        worker["last_event_id"] = event.event_id
        if "error" in payload:
            worker["error"] = payload["error"]
        if "reason" in payload:
            worker["reason"] = payload["reason"]
        agent_id = worker.get("agent_id")
        if isinstance(agent_id, str) and agent_id in state.agents:
            state.agents[agent_id]["status"] = status
            state.agents[agent_id]["last_event_id"] = event.event_id

    def _apply_worker_result_handoff(self, state: RunState, payload: dict[str, Any], event: CanonicalEvent) -> None:
        worker_id = str(payload["worker_id"])
        worker = state.workers.setdefault(worker_id, {"worker_id": worker_id})
        result_refs = worker.setdefault("result_refs", [])
        result_refs.append(dict(payload["artifact_ref"]))
        worker["result_summary"] = payload["summary"]
        worker["last_event_id"] = event.event_id

    def _apply_workspace_bound(self, state: RunState, payload: dict[str, Any], event: CanonicalEvent) -> None:
        workspace_id = str(payload["workspace_id"])
        existing = state.workspaces.get(workspace_id, {})
        provenance = dict(payload["provenance"])
        state.workspaces[workspace_id] = {
            "workspace_id": workspace_id,
            "run_id": payload["run_id"],
            "mode": payload["mode"],
            "bound_to": dict(payload["bound_to"]),
            "lease_status": payload["lease_status"],
            "granted_by": dict(payload.get("granted_by") or {"decision_id": provenance["decision_id"]}),
            "created_by": dict(payload.get("created_by") or existing.get("created_by") or {}),
            "released_by": existing.get("released_by"),
            "released_at": existing.get("released_at"),
            "artifact_refs": list(existing.get("artifact_refs", [])),
            "provenance": provenance,
            "basis_event_id": event.event_id,
            "last_event_id": event.event_id,
        }

    def _apply_workspace_lease_created(self, state: RunState, payload: dict[str, Any], event: CanonicalEvent) -> None:
        workspace_id = str(payload["workspace_id"])
        state.workspaces[workspace_id] = {
            "workspace_id": workspace_id,
            "run_id": payload["run_id"],
            "mode": payload["mode"],
            "bound_to": dict(payload["bound_to"]),
            "lease_status": payload["lease_status"],
            "granted_by": dict(payload["granted_by"]),
            "created_by": dict(payload["created_by"]),
            "released_by": None,
            "released_at": None,
            "artifact_refs": [],
            "provenance": dict(payload["provenance"]),
            "basis_event_id": event.event_id,
            "last_event_id": event.event_id,
        }

    def _apply_workspace_released(self, state: RunState, payload: dict[str, Any], event: CanonicalEvent) -> None:
        workspace_id = str(payload["workspace_id"])
        workspace_entry = state.workspaces.setdefault(
            workspace_id,
            {
                "workspace_id": workspace_id,
                "run_id": payload["run_id"],
                "artifact_refs": [],
                "provenance": {},
            },
        )
        workspace_entry["lease_status"] = "released"
        workspace_entry["released_by"] = dict(payload["released_by"])
        workspace_entry["released_at"] = payload["released_at"]
        workspace_entry["release_reason"] = payload.get("reason")
        workspace_entry["release_basis_event_id"] = payload["basis_event_id"]
        workspace_entry["basis_event_id"] = event.event_id
        workspace_entry["last_event_id"] = event.event_id

    def _apply_workspace_artifact_captured(
        self,
        state: RunState,
        payload: dict[str, Any],
        event: CanonicalEvent,
    ) -> None:
        workspace_id = str(payload["workspace_id"])
        workspace_entry = state.workspaces.setdefault(
            workspace_id,
            {
                "workspace_id": workspace_id,
                "run_id": payload["run_id"],
                "artifact_refs": [],
                "provenance": {},
            },
        )
        artifact_ref = dict(payload["artifact_ref"])
        artifact_refs = workspace_entry.setdefault("artifact_refs", [])
        if not any(
            self._stable_json(existing_ref) == self._stable_json(artifact_ref)
            for existing_ref in artifact_refs
        ):
            artifact_refs.append(artifact_ref)
        capture_provenance = workspace_entry.setdefault("artifact_capture_provenance", [])
        capture_provenance.append(
            {
                "artifact_ref": artifact_ref,
                "captured_by": dict(payload["captured_by"]),
                "provenance": dict(payload["provenance"]),
                "basis_event_id": event.event_id,
            }
        )
        workspace_entry["basis_event_id"] = event.event_id
        workspace_entry["last_event_id"] = event.event_id

    def _apply_snapshot_imported(self, state: RunState, payload: dict[str, Any]) -> None:
        source_ref = dict(payload["source_ref"])
        provenance = dict(payload["provenance"])
        observation = _ObservationDict(
            {
                "snapshot_id": payload["snapshot_id"],
                "snapshot_type": payload["content_type"],
                "source_system": payload["source_system"],
                "captured_at": payload["captured_at"],
                "content_type": payload["content_type"],
                "source_ref": source_ref,
                "summary": payload["summary"],
                "observation": dict(payload["observation"]),
                "quality": dict(payload["quality"]),
                "provenance": provenance,
                "basis_refs": [dict(ref) for ref in payload["basis_refs"]],
                "status": "imported",
                "conflict_status": "none",
            }
        )
        if "run_status" in observation["observation"]:
            observation["native_status"] = state.status
        existing = self._find_external_observation(state.external_observations, observation["snapshot_id"])
        if existing is not None:
            self._merge_duplicate_external_observation(existing, observation)
            self._mark_snapshot_conflicts(state.external_observations)
            return
        state.external_observations.append(observation)
        self._mark_snapshot_conflicts(state.external_observations)

    def _find_external_observation(
        self,
        observations: list[dict[str, Any]],
        snapshot_id: Any,
    ) -> dict[str, Any] | None:
        for observation in observations:
            if observation.get("snapshot_id") == snapshot_id:
                return observation
        return None

    def _merge_duplicate_external_observation(
        self,
        existing: dict[str, Any],
        incoming: dict[str, Any],
    ) -> None:
        if existing.get("observation") != incoming.get("observation"):
            existing["conflict_status"] = "conflict"
            existing["status"] = "conflict"
        self._merge_basis_refs(existing, incoming.get("basis_refs", []))

    def _merge_basis_refs(self, observation: dict[str, Any], refs: list[Any]) -> None:
        existing_refs = observation.setdefault("basis_refs", [])
        seen = {self._stable_json(ref) for ref in existing_refs}
        for ref in refs:
            key = self._stable_json(ref)
            if key not in seen:
                existing_refs.append(dict(ref))
                seen.add(key)

    def _stable_json(self, value: Any) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    def _mark_snapshot_conflicts(self, observations: list[dict[str, Any]]) -> None:
        by_subject: dict[str, dict[str, Any]] = {}
        conflicted_subjects: set[str] = set()
        for observation in observations:
            subject_key = self._external_observation_subject_key(observation)
            previous = by_subject.get(subject_key)
            if previous is not None and previous.get("observation") != observation.get("observation"):
                conflicted_subjects.add(subject_key)
            else:
                by_subject.setdefault(subject_key, observation)
        for observation in observations:
            if observation.get("conflict_status") == "conflict":
                observation["status"] = "conflict"
            elif observation.get("status") != "conflict":
                observation["status"] = "imported"
            if self._external_observation_subject_key(observation) in conflicted_subjects:
                observation["conflict_status"] = "conflict"
                observation["status"] = "conflict"

    def _external_observation_subject_key(self, observation: dict[str, Any]) -> str:
        observed = observation.get("observation")
        subject = observed.get("subject") if isinstance(observed, dict) else None
        return self._stable_json(
            {
                "snapshot_type": observation.get("snapshot_type") or observation.get("content_type"),
                "subject": subject if subject is not None else observation.get("content_type"),
            }
        )
