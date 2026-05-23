"""RunProjector rebuild and checkpoint helpers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Iterable

from ..events.events import EVENT_ENVELOPE_VERSION, CanonicalEvent
from .projector_state import RunState


PROJECTOR_VERSION = "run_projector@v1"


def _facade_datetime():
    from . import projector

    return getattr(projector, "datetime", datetime)


class RunProjectorCheckpointMixin:
    """Rebuild RunState from events and checkpoint snapshots."""

    def project(self, events: Iterable[CanonicalEvent]) -> RunState:
        self._proposal_outcomes = {}
        self._proposal_action_types = {}
        self._proposal_reason_codes = {}
        self._proposal_summaries = {}
        self._proposal_agents = {}
        self._proposal_grants = {}
        self._proposal_registry_basis = {}
        self._proposal_policy_basis = {}
        self._execution_statuses = {}
        self._execution_action_types = {}
        self._execution_proposals = {}
        self._proposal_execution_ids = {}
        self._proposal_start_event_ids = {}
        self._retry_requests = {}
        self._cancel_requests = {}
        self._approval_proposals = {}
        self._approval_resolutions = set()
        self._delegation_proposals = {}
        self._delegation_decisions = {}
        self._workers = {}
        self._worker_agent_ids = set()
        self._memory_record_ids = set()
        self._workspace_statuses = {}
        self._workspace_last_event_ids = {}
        self._artifact_ref_event_ids = {}
        self._run_completed = False
        state = RunState()
        for event in events:
            self._validate_lifecycle(event)
            self.apply(state, event)
        return state

    def rebuild(self, run_id: str, event_store) -> RunState:
        return self.project(event_store.list_events(run_id))

    def save_checkpoint(
        self,
        run_id: str,
        event_store,
        checkpoint_store,
        projector_version: str = PROJECTOR_VERSION,
    ) -> dict[str, Any]:
        canonical_events = event_store.list_events(run_id)
        checkpoint = self.create_checkpoint(run_id, canonical_events, projector_version)
        return checkpoint_store.save_checkpoint(run_id, checkpoint)

    def save_checkpoint_history(
        self,
        run_id: str,
        event_store,
        checkpoint_store,
        projector_version: str = PROJECTOR_VERSION,
    ) -> dict[str, Any]:
        canonical_events = event_store.list_events(run_id)
        checkpoint = self.create_checkpoint(run_id, canonical_events, projector_version)
        return checkpoint_store.save_checkpoint_history(run_id, checkpoint)

    def create_checkpoint(
        self,
        run_id: str,
        events: Iterable[CanonicalEvent],
        projector_version: str = PROJECTOR_VERSION,
    ) -> dict[str, Any]:
        canonical_events = list(events)
        if not canonical_events:
            raise ValueError("cannot create checkpoint from empty events")

        state = self.project(canonical_events)
        if state.run_id and state.run_id != run_id:
            raise ValueError("checkpoint state run_id must match checkpoint run_id")

        checkpoint = {
            "run_id": run_id,
            "projector_version": projector_version,
            "basis_event_id": canonical_events[-1].event_id,
            "state": self._checkpoint_state_payload(state),
            "created_at": _facade_datetime().now(timezone.utc).isoformat(),
        }
        checkpoint["integrity"] = {
            "algorithm": "sha256",
            "checkpoint_hash": self._checkpoint_hash(self._checkpoint_payload_for_hash(checkpoint)),
            "event_digest_algorithm": "sha256",
            "event_prefix_digest": self._event_prefix_digest(canonical_events),
            "event_digest_basis_event_id": checkpoint["basis_event_id"],
            "event_digest_event_count": len(canonical_events),
            "event_digest_event_envelope_version": EVENT_ENVELOPE_VERSION,
        }
        return checkpoint

    def rebuild_with_checkpoint(
        self,
        run_id: str,
        event_store,
        checkpoint_store,
        projector_version: str = PROJECTOR_VERSION,
    ) -> RunState:
        candidates = self._load_checkpoint_candidates(run_id, checkpoint_store)
        if not candidates:
            return self.rebuild(run_id, event_store)

        canonical_events = event_store.list_events(run_id)
        for checkpoint in candidates:
            state = self._try_rebuild_from_checkpoint(
                run_id,
                canonical_events,
                checkpoint,
                projector_version,
            )
            if state is not None:
                return state
        return self.rebuild(run_id, event_store)

    def _load_checkpoint_candidates(self, run_id: str, checkpoint_store) -> list[dict[str, Any]]:
        if hasattr(checkpoint_store, "load_checkpoint_candidates"):
            return checkpoint_store.load_checkpoint_candidates(run_id)
        checkpoint = checkpoint_store.load_latest_checkpoint(run_id)
        return [] if checkpoint is None else [checkpoint]

    def _try_rebuild_from_checkpoint(
        self,
        run_id: str,
        canonical_events: list[CanonicalEvent],
        checkpoint: dict[str, Any],
        projector_version: str,
    ) -> RunState | None:
        if not self._is_compatible_projector_version(checkpoint, projector_version):
            return None
        if checkpoint["run_id"] != run_id:
            return None
        if not self._validate_checkpoint_integrity(checkpoint):
            return None

        basis_index = self._find_basis_index(canonical_events, checkpoint["basis_event_id"])
        if not self._validate_event_prefix_digest(checkpoint, canonical_events, basis_index):
            return None

        # Validate prefix from canonical events before trusting the checkpoint state.
        prefix_state = self.project(canonical_events[: basis_index + 1])
        state = self._run_state_from_checkpoint(checkpoint["state"], run_id, checkpoint["basis_event_id"])
        if state != prefix_state:
            return None

        for event in canonical_events[basis_index + 1 :]:
            self._validate_lifecycle(event)
            self.apply(state, event)
        return state

    def _checkpoint_payload_for_hash(self, checkpoint: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in checkpoint.items()
            if key not in {"integrity", "checkpoint_hash"}
        }

    def _checkpoint_state_payload(self, state: RunState) -> dict[str, Any]:
        state_payload = asdict(state)
        return {field_name: state_payload[field_name] for field_name in self.CHECKPOINT_STATE_FIELDS}

    def _is_compatible_projector_version(self, checkpoint: dict[str, Any], projector_version: Any) -> bool:
        checkpoint_version = checkpoint.get("projector_version")
        if not isinstance(checkpoint_version, str) or not checkpoint_version:
            return False
        if not isinstance(projector_version, str) or not projector_version:
            return False
        return checkpoint_version == projector_version

    def _checkpoint_hash(self, checkpoint_without_integrity: dict[str, Any]) -> str:
        encoded = json.dumps(
            checkpoint_without_integrity,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _validate_checkpoint_integrity(self, checkpoint: dict[str, Any]) -> bool:
        integrity = checkpoint.get("integrity")
        if integrity is None:
            return True
        if not isinstance(integrity, dict):
            return False
        if integrity.get("algorithm") != "sha256":
            return False
        checkpoint_hash = integrity.get("checkpoint_hash")
        if not isinstance(checkpoint_hash, str) or not checkpoint_hash:
            return False
        expected = self._checkpoint_hash(self._checkpoint_payload_for_hash(checkpoint))
        return checkpoint_hash == expected

    def _event_prefix_payload(self, canonical_events: list[CanonicalEvent]) -> list[dict[str, Any]]:
        return [
            {
                "event_id": event.event_id,
                "run_id": event.run_id,
                "event_type": event.event_type,
                "payload": event.payload,
                "created_at": event.created_at,
                "event_envelope_version": event.event_envelope_version,
            }
            for event in canonical_events
        ]

    def _event_prefix_digest(self, canonical_events: list[CanonicalEvent]) -> str:
        encoded = json.dumps(
            self._event_prefix_payload(canonical_events),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _validate_event_prefix_digest(
        self,
        checkpoint: dict[str, Any],
        canonical_events: list[CanonicalEvent],
        basis_index: int,
    ) -> bool:
        integrity = checkpoint.get("integrity")
        if not isinstance(integrity, dict):
            return True
        if "event_prefix_digest" not in integrity:
            return True
        if integrity.get("event_digest_algorithm") != "sha256":
            return False
        event_prefix_digest = integrity.get("event_prefix_digest")
        if not isinstance(event_prefix_digest, str) or not event_prefix_digest:
            return False
        if integrity.get("event_digest_basis_event_id") != checkpoint["basis_event_id"]:
            return False
        event_count = integrity.get("event_digest_event_count")
        if not isinstance(event_count, int) or isinstance(event_count, bool):
            return False
        if event_count != basis_index + 1:
            return False
        event_envelope_version = integrity.get("event_digest_event_envelope_version")
        if event_envelope_version is not None and event_envelope_version != EVENT_ENVELOPE_VERSION:
            return False
        expected = self._event_prefix_digest(canonical_events[: basis_index + 1])
        return event_prefix_digest == expected

    def _find_basis_index(self, canonical_events: list[CanonicalEvent], basis_event_id: str) -> int:
        for index, event in enumerate(canonical_events):
            if event.event_id == basis_event_id:
                return index
        raise ValueError("checkpoint basis_event_id not found")

    def _run_state_from_checkpoint(self, state: dict[str, Any], run_id: str, basis_event_id: str) -> RunState:
        if not isinstance(state, dict):
            raise ValueError("checkpoint state must be a dict")
        for field in self.CHECKPOINT_REQUIRED_STATE_FIELDS:
            if field not in state:
                raise ValueError(f"checkpoint state missing required field: {field}")
        if state["run_id"] != run_id:
            raise ValueError("checkpoint state run_id must match rebuild run_id")
        if state["last_event_id"] != basis_event_id:
            raise ValueError("checkpoint state last_event_id must match basis_event_id")
        if state["status"] not in self.KNOWN_RUN_STATUSES:
            raise ValueError("checkpoint state status must be known")
        agents = state.get("agents", {})
        if not isinstance(agents, dict):
            raise ValueError("checkpoint state agents must be a dict")
        delegations = state.get("delegations", {})
        if not isinstance(delegations, dict):
            raise ValueError("checkpoint state delegations must be a dict")
        workers = state.get("workers", {})
        if not isinstance(workers, dict):
            raise ValueError("checkpoint state workers must be a dict")
        workspaces = state.get("workspaces", {})
        if not isinstance(workspaces, dict):
            raise ValueError("checkpoint state workspaces must be a dict")
        if not isinstance(state["actions"], dict):
            raise ValueError("checkpoint state actions must be a dict")
        action_retries = state.get("action_retries", {})
        if not isinstance(action_retries, dict):
            raise ValueError("checkpoint state action_retries must be a dict")
        action_cancellations = state.get("action_cancellations", {})
        if not isinstance(action_cancellations, dict):
            raise ValueError("checkpoint state action_cancellations must be a dict")
        action_supersessions = state.get("action_supersessions", {})
        if not isinstance(action_supersessions, dict):
            raise ValueError("checkpoint state action_supersessions must be a dict")
        approvals = state.get("approvals", {})
        if not isinstance(approvals, dict):
            raise ValueError("checkpoint state approvals must be a dict")
        if not isinstance(state["artifacts"], list):
            raise ValueError("checkpoint state artifacts must be a list")
        memory_records = state.get("memory_records", [])
        if not isinstance(memory_records, list):
            raise ValueError("checkpoint state memory_records must be a list")
        external_observations = state.get("external_observations", [])
        if not isinstance(external_observations, list):
            raise ValueError("checkpoint state external_observations must be a list")
        for artifact in state["artifacts"]:
            self._validate_checkpoint_artifact(artifact)
        for agent_id, agent in agents.items():
            self._validate_checkpoint_agent(agent_id, agent)
        for delegation_id, delegation in delegations.items():
            self._validate_checkpoint_delegation(delegation_id, delegation)
        for worker_id, worker in workers.items():
            self._validate_checkpoint_worker(worker_id, worker)
        for workspace_id, workspace in workspaces.items():
            self._validate_checkpoint_workspace(workspace_id, workspace)
        for approval_id, approval in approvals.items():
            self._validate_checkpoint_approval(approval_id, approval)
        for record in memory_records:
            self._validate_checkpoint_memory_record(record)
        for observation in external_observations:
            self._validate_checkpoint_external_observation(observation)
        return RunState(
            run_id=str(state.get("run_id", "")),
            session_id=str(state.get("session_id", "")),
            goal=str(state.get("goal", "")),
            status=str(state.get("status", "unknown")),
            created_event_id=str(state.get("created_event_id", "")),
            completed_event_id=str(state.get("completed_event_id", "")),
            current_agent=str(state.get("current_agent", "")),
            agents=dict(agents),
            delegations=dict(delegations),
            workers=dict(workers),
            workspaces=dict(workspaces),
            actions=dict(state.get("actions", {})),
            action_retries=dict(action_retries),
            action_cancellations=dict(action_cancellations),
            action_supersessions=dict(action_supersessions),
            approvals=dict(approvals),
            artifacts=list(state.get("artifacts", [])),
            memory_records=list(memory_records),
            external_observations=list(external_observations),
            last_event_id=str(state.get("last_event_id", "")),
        )

    def _validate_checkpoint_agent(self, agent_id: Any, agent: Any) -> None:
        if not isinstance(agent_id, str) or not agent_id:
            raise ValueError("checkpoint agent id must be a non-empty string")
        if not isinstance(agent, dict):
            raise ValueError("checkpoint agent entry must be a dict")
        if agent.get("agent_id") != agent_id:
            raise ValueError("checkpoint agent id must match entry agent_id")
        if not isinstance(agent.get("role"), str) or not agent["role"]:
            raise ValueError("checkpoint agent role must be a non-empty string")
        if agent.get("status") not in {"created", "running", "completed", "failed", "cancelled"}:
            raise ValueError("checkpoint agent status must be known")

    def _validate_checkpoint_delegation(self, delegation_id: Any, delegation: Any) -> None:
        if not isinstance(delegation_id, str) or not delegation_id:
            raise ValueError("checkpoint delegation id must be a non-empty string")
        if not isinstance(delegation, dict):
            raise ValueError("checkpoint delegation entry must be a dict")
        for field_name in (
            "delegation_id",
            "parent_agent_id",
            "requested_worker_role",
            "requested_capabilities",
            "status",
        ):
            if field_name not in delegation:
                raise ValueError(f"checkpoint delegation entry missing required field: {field_name}")
        if delegation["delegation_id"] != delegation_id:
            raise ValueError("checkpoint delegation id must match entry delegation_id")
        if not isinstance(delegation["requested_capabilities"], dict):
            raise ValueError("checkpoint delegation requested_capabilities must be a dict")
        if delegation["status"] not in {"proposed", "approved", "modified", "denied"}:
            raise ValueError("checkpoint delegation status must be known")
        if "decision_id" in delegation:
            if not isinstance(delegation.get("grants"), dict):
                raise ValueError("checkpoint delegation grants must be a dict")
            reason_codes = delegation.get("reason_codes", [])
            if not isinstance(reason_codes, list) or not all(isinstance(code, str) for code in reason_codes):
                raise ValueError("checkpoint delegation reason_codes must be a list of strings")
            if not isinstance(delegation.get("policy_basis", {}), dict):
                raise ValueError("checkpoint delegation policy_basis must be a dict")

    def _validate_checkpoint_worker(self, worker_id: Any, worker: Any) -> None:
        if not isinstance(worker_id, str) or not worker_id:
            raise ValueError("checkpoint worker id must be a non-empty string")
        if not isinstance(worker, dict):
            raise ValueError("checkpoint worker entry must be a dict")
        for field_name in (
            "worker_id",
            "agent_id",
            "parent_agent_id",
            "delegation_id",
            "decision_id",
            "status",
            "grants",
            "workspace",
        ):
            if field_name not in worker:
                raise ValueError(f"checkpoint worker entry missing required field: {field_name}")
        if worker["worker_id"] != worker_id:
            raise ValueError("checkpoint worker id must match entry worker_id")
        if worker["status"] not in {"created", "running", "completed", "failed", "cancelled"}:
            raise ValueError("checkpoint worker status must be known")
        if not isinstance(worker["grants"], dict):
            raise ValueError("checkpoint worker grants must be a dict")
        if not isinstance(worker["workspace"], dict):
            raise ValueError("checkpoint worker workspace must be a dict")
        result_refs = worker.get("result_refs", [])
        if not isinstance(result_refs, list):
            raise ValueError("checkpoint worker result_refs must be a list")
        for index, ref in enumerate(result_refs):
            self._validate_resource_ref_payload(ref, f"checkpoint worker result_refs[{index}]")

    def _validate_checkpoint_workspace(self, workspace_id: Any, workspace: Any) -> None:
        if not isinstance(workspace_id, str) or not workspace_id:
            raise ValueError("checkpoint workspace id must be a non-empty string")
        if not isinstance(workspace, dict):
            raise ValueError("checkpoint workspace entry must be a dict")
        for field_name in self.CHECKPOINT_WORKSPACE_FORBIDDEN_FIELDS:
            if field_name in workspace:
                raise ValueError(f"checkpoint workspace entry cannot contain {field_name}")
        for field_name in ("workspace_id", "run_id", "mode", "bound_to", "lease_status", "provenance", "basis_event_id"):
            if field_name not in workspace:
                raise ValueError(f"checkpoint workspace entry missing required field: {field_name}")
        if workspace["workspace_id"] != workspace_id:
            raise ValueError("checkpoint workspace id must match entry workspace_id")
        if workspace["mode"] != "shared_ro":
            raise ValueError("checkpoint workspace mode must be shared_ro")
        if workspace["lease_status"] not in self.KNOWN_WORKSPACE_LEASE_STATUSES:
            raise ValueError("checkpoint workspace lease_status must be known")
        if not isinstance(workspace["bound_to"], dict):
            raise ValueError("checkpoint workspace bound_to must be a dict")
        if not any(
            isinstance(workspace["bound_to"].get(field_name), str) and workspace["bound_to"][field_name]
            for field_name in ("agent_id", "execution_id", "worker_id")
        ):
            raise ValueError("checkpoint workspace bound_to must include agent_id, execution_id, or worker_id")
        if not isinstance(workspace["provenance"], dict):
            raise ValueError("checkpoint workspace provenance must be a dict")
        if not isinstance(workspace["basis_event_id"], str) or not workspace["basis_event_id"]:
            raise ValueError("checkpoint workspace basis_event_id must be a non-empty string")
        last_event_id = workspace.get("last_event_id")
        if last_event_id is not None and (not isinstance(last_event_id, str) or not last_event_id):
            raise ValueError("checkpoint workspace last_event_id must be a non-empty string")
        artifact_refs = workspace.get("artifact_refs", [])
        if not isinstance(artifact_refs, list):
            raise ValueError("checkpoint workspace artifact_refs must be a list")
        for index, ref in enumerate(artifact_refs):
            self._validate_resource_ref_payload(ref, f"checkpoint workspace artifact_refs[{index}]")
        capture_provenance = workspace.get("artifact_capture_provenance", [])
        if not isinstance(capture_provenance, list):
            raise ValueError("checkpoint workspace artifact_capture_provenance must be a list")
        for entry in capture_provenance:
            if not isinstance(entry, dict):
                raise ValueError("checkpoint workspace artifact_capture_provenance entry must be a dict")
            if "artifact_ref" in entry:
                self._validate_resource_ref_payload(
                    entry["artifact_ref"],
                    "checkpoint workspace artifact_capture_provenance artifact_ref",
                )

    def _validate_checkpoint_artifact(self, artifact: Any) -> None:
        if not isinstance(artifact, dict):
            raise ValueError("checkpoint artifact entry must be a dict")
        if "content" in artifact:
            raise ValueError("checkpoint artifact entry cannot contain content")
        for field in self.CHECKPOINT_ARTIFACT_FIELDS:
            if field not in artifact:
                raise ValueError(f"checkpoint artifact entry missing required field: {field}")
        for field_name in ("basis_refs", "source_refs"):
            refs = artifact.get(field_name, [])
            if not isinstance(refs, list):
                raise ValueError(f"checkpoint artifact {field_name} must be a list")
            for index, ref in enumerate(refs):
                self._validate_resource_ref_payload(ref, f"checkpoint artifact {field_name}[{index}]")

    def _validate_checkpoint_approval(self, approval_id: Any, approval: Any) -> None:
        if not isinstance(approval_id, str) or not approval_id:
            raise ValueError("checkpoint approval id must be a non-empty string")
        if not isinstance(approval, dict):
            raise ValueError("checkpoint approval entry must be a dict")
        for field_name in ("approval_id", "run_id", "proposal_id", "decision_id", "status"):
            if field_name not in approval:
                raise ValueError(f"checkpoint approval entry missing required field: {field_name}")
        if approval["approval_id"] != approval_id:
            raise ValueError("checkpoint approval id must match entry approval_id")
        status = approval["status"]
        if status not in {"pending", "approved", "denied"}:
            raise ValueError("checkpoint approval status must be known")
        if status == "pending":
            reason_codes = approval.get("reason_codes")
            if not isinstance(reason_codes, list):
                raise ValueError("checkpoint pending approval reason_codes must be a list")
            if not isinstance(approval.get("requested_action_summary"), dict):
                raise ValueError("checkpoint pending approval requested_action_summary must be a dict")
        else:
            if approval.get("resolution") != status:
                raise ValueError("checkpoint resolved approval resolution must match status")
            for field_name in ("reason", "resolver", "resolved_event_id"):
                value = approval.get(field_name)
                if not isinstance(value, str) or not value:
                    raise ValueError(f"checkpoint resolved approval missing required field: {field_name}")

    def _validate_checkpoint_memory_record(self, record: Any) -> None:
        if not isinstance(record, dict):
            raise ValueError("checkpoint memory record entry must be a dict")
        for field_name in self.CHECKPOINT_MEMORY_RECORD_FORBIDDEN_FIELDS:
            if field_name in record:
                raise ValueError(f"checkpoint memory record entry cannot contain {field_name}")
        for field_name in self.CHECKPOINT_MEMORY_RECORD_FIELDS:
            if field_name not in record:
                raise ValueError(f"checkpoint memory record entry missing required field: {field_name}")
        if not isinstance(record["source_refs"], list):
            raise ValueError("checkpoint memory record source_refs must be a list")
        if not isinstance(record["provenance"], dict):
            raise ValueError("checkpoint memory record provenance must be a dict")
        unexpected_fields = set(record) - self.CHECKPOINT_MEMORY_RECORD_ALLOWED_FIELDS
        if unexpected_fields:
            field_name = sorted(unexpected_fields)[0]
            raise ValueError(f"checkpoint memory record entry has unknown field: {field_name}")
        self._validate_checkpoint_memory_supersession(record)

    def _validate_checkpoint_memory_supersession(self, record: dict[str, Any]) -> None:
        supersession_fields = ("superseded_by", "superseded_event_id", "superseded_reason")
        has_supersession = record.get("status") == "superseded" or any(field in record for field in supersession_fields)
        if not has_supersession:
            return
        for field_name in supersession_fields:
            if field_name not in record:
                raise ValueError(f"checkpoint superseded memory record missing required field: {field_name}")
        if not isinstance(record["superseded_by"], str):
            raise ValueError("checkpoint superseded_by must be a string")
        if not isinstance(record["superseded_event_id"], str):
            raise ValueError("checkpoint superseded_event_id must be a string")
        if not isinstance(record["superseded_reason"], str) or not record["superseded_reason"]:
            raise ValueError("checkpoint superseded_reason must be a non-empty string")

    def _validate_checkpoint_external_observation(self, observation: Any) -> None:
        if not isinstance(observation, dict):
            raise ValueError("checkpoint external observation entry must be a dict")
        for field_name in self.CHECKPOINT_EXTERNAL_OBSERVATION_FORBIDDEN_FIELDS:
            if field_name in observation:
                raise ValueError(f"checkpoint external observation entry cannot contain {field_name}")
        for field_name in self.CHECKPOINT_EXTERNAL_OBSERVATION_FIELDS:
            if field_name not in observation:
                raise ValueError(f"checkpoint external observation entry missing required field: {field_name}")
        if observation["status"] not in {"imported", "conflict"}:
            raise ValueError("checkpoint external observation status must be imported or conflict")
        if observation["conflict_status"] not in {"none", "conflict"}:
            raise ValueError("checkpoint external observation conflict_status must be known")
        self._validate_resource_ref_payload(observation["source_ref"], "checkpoint external observation source_ref")
        if not isinstance(observation["observation"], dict):
            raise ValueError("checkpoint external observation observation must be a dict")
        for field_name in self.CHECKPOINT_EXTERNAL_OBSERVATION_FORBIDDEN_FIELDS:
            if field_name in observation["observation"]:
                raise ValueError(f"checkpoint external observation observation cannot contain {field_name}")
        quality = observation["quality"]
        if not isinstance(quality, dict):
            raise ValueError("checkpoint external observation quality must be a dict")
        for field_name in ("confidence", "coverage", "freshness"):
            if field_name not in quality:
                raise ValueError(f"checkpoint external observation quality missing required field: {field_name}")
        provenance = observation["provenance"]
        if not isinstance(provenance, dict):
            raise ValueError("checkpoint external observation provenance must be a dict")
        for field_name in self.CHECKPOINT_EXTERNAL_OBSERVATION_FORBIDDEN_FIELDS:
            if field_name in provenance:
                raise ValueError(f"checkpoint external observation provenance cannot contain {field_name}")
        raw_artifact_ref = provenance.get("raw_artifact_ref")
        self._validate_resource_ref_payload(raw_artifact_ref, "checkpoint external observation raw_artifact_ref")
        basis_refs = observation["basis_refs"]
        if not isinstance(basis_refs, list) or not basis_refs:
            raise ValueError("checkpoint external observation basis_refs must be a non-empty list")
        for index, ref in enumerate(basis_refs):
            self._validate_resource_ref_payload(ref, f"checkpoint external observation basis_refs[{index}]")
