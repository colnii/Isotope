"""RunState projector boundary for the Isotope v0.1 slice."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

from .events import EVENT_ENVELOPE_VERSION, CanonicalEvent


@dataclass
class RunState:
    """In-memory read model for the v0.1 slice, not a source of truth."""

    run_id: str = ""
    status: str = "unknown"
    current_agent: str = ""
    actions: dict[str, dict[str, Any]] = field(default_factory=dict)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    memory_records: list[dict[str, Any]] = field(default_factory=list)
    last_event_id: str = ""


class RunProjector:
    """Project RunState only from canonical events."""

    EXECUTABLE_DECISION_OUTCOMES = {"approved", "modified"}
    KNOWN_DECISION_OUTCOMES = {"approved", "modified", "denied", "pending_user_approval"}
    KNOWN_RUN_STATUSES = {"unknown", "running", "pending_user_approval", "failed", "completed"}
    CHECKPOINT_STATE_FIELDS = (
        "run_id",
        "status",
        "current_agent",
        "actions",
        "artifacts",
        "memory_records",
        "last_event_id",
    )
    CHECKPOINT_REQUIRED_STATE_FIELDS = ("run_id", "status", "current_agent", "actions", "artifacts", "last_event_id")
    CHECKPOINT_ARTIFACT_FIELDS = ("ref", "artifact_type", "summary", "provenance")
    CHECKPOINT_MEMORY_RECORD_FIELDS = ("record_id", "summary", "source_refs", "provenance")
    CHECKPOINT_MEMORY_RECORD_FORBIDDEN_FIELDS = ("content", "full_content", "artifact_content", "raw_content")
    CHECKPOINT_MEMORY_RECORD_ALLOWED_FIELDS = {
        "record_id",
        "execution_id",
        "summary",
        "source_refs",
        "provenance",
        "basis_event_id",
        "quality",
        "status",
        "superseded_by",
        "superseded_event_id",
        "superseded_reason",
    }
    PROJECTOR_VERSION = "run_projector@v1"

    def __init__(self) -> None:
        self._proposal_outcomes: dict[str, str] = {}
        self._proposal_action_types: dict[str, str] = {}
        self._execution_statuses: dict[str, str] = {}
        self._execution_action_types: dict[str, str] = {}
        self._memory_record_ids: set[str] = set()
        self._run_completed = False

    def _validate_lifecycle(self, event: CanonicalEvent) -> None:
        payload = event.payload
        self._validate_event_payload(event)
        if self._run_completed and event.event_type in {
            "action.decided",
            "action.started",
            "action.failed",
            "action.completed",
            "artifact.created",
            "memory.record_created",
            "memory.record_superseded",
        }:
            raise ValueError("event after run.completed")

        if event.event_type == "action.proposed":
            proposal_id = payload.get("proposal_id")
            action_type = payload.get("action_type")
            if isinstance(proposal_id, str) and isinstance(action_type, str):
                self._proposal_action_types[proposal_id] = action_type
        elif event.event_type == "action.decided":
            self._proposal_outcomes[str(payload["proposal_id"])] = str(payload["outcome"])
        elif event.event_type == "action.started":
            proposal_id = str(payload["proposal_id"])
            outcome = self._proposal_outcomes.get(proposal_id)
            if outcome == "denied":
                raise ValueError("action.started after denied decision")
            if outcome == "pending_user_approval":
                raise ValueError("action.started after pending approval")
            if outcome not in self.EXECUTABLE_DECISION_OUTCOMES:
                raise ValueError("action.started before approved decision")
            self._execution_statuses[str(payload["execution_id"])] = "running"
            self._execution_action_types[str(payload["execution_id"])] = self._proposal_action_types.get(proposal_id, "")
        elif event.event_type == "action.completed":
            execution_id = str(payload["execution_id"])
            status = self._execution_statuses.get(execution_id)
            if status is None:
                raise ValueError("action.completed before action.started")
            if status == "failed":
                raise ValueError("terminal execution already failed")
            self._execution_statuses[execution_id] = "completed"
        elif event.event_type == "action.failed":
            execution_id = str(payload["execution_id"])
            status = self._execution_statuses.get(execution_id)
            if status == "completed":
                raise ValueError("terminal execution already completed")
            self._execution_statuses[execution_id] = "failed"
        elif event.event_type == "memory.record_created":
            self._validate_memory_record_lifecycle(payload)
            self._memory_record_ids.add(str(payload["record_id"]))
        elif event.event_type == "memory.record_superseded":
            self._validate_memory_record_superseded_lifecycle(payload)
        elif event.event_type == "run.completed":
            self._validate_run_completed()
            self._run_completed = True

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

    def _validate_event_payload(self, event: CanonicalEvent) -> None:
        payload = event.payload
        if event.event_type == "action.decided":
            self._require_fields(event.event_type, payload, ("proposal_id", "decision_id", "outcome"))
            if payload["outcome"] not in self.KNOWN_DECISION_OUTCOMES:
                raise ValueError("action.decided has unknown outcome")
        elif event.event_type == "action.started":
            self._require_fields(event.event_type, payload, ("execution_id", "proposal_id", "decision_id"))
        elif event.event_type == "action.completed":
            self._require_fields(event.event_type, payload, ("execution_id", "status", "artifact_refs"))
            if payload["status"] != "completed":
                raise ValueError("action.completed status must be completed")
            if not isinstance(payload["artifact_refs"], list):
                raise ValueError("action.completed artifact_refs must be a list")
        elif event.event_type == "action.failed":
            self._require_fields(event.event_type, payload, ("execution_id", "proposal_id", "decision_id", "status"))
            if payload["status"] != "failed":
                raise ValueError("action.failed status must be failed")
        elif event.event_type == "artifact.created":
            self._require_fields(event.event_type, payload, ("artifact",))
            artifact = payload["artifact"]
            if not isinstance(artifact, dict):
                raise ValueError("artifact.created artifact must be a dict")
            self._require_fields(
                "artifact.created artifact",
                artifact,
                ("ref", "artifact_type", "summary", "provenance"),
            )
            if "content" in artifact:
                raise ValueError("artifact.created artifact cannot contain content")
        elif event.event_type == "approval.requested":
            self._require_fields(
                event.event_type,
                payload,
                ("approval_id", "proposal_id", "decision_id", "action_type"),
            )
        elif event.event_type == "memory.record_created":
            self._validate_memory_record_created_payload(payload)
        elif event.event_type == "memory.record_superseded":
            self._validate_memory_record_superseded_payload(payload)

    def _require_fields(self, label: str, payload: dict[str, Any], fields: tuple[str, ...]) -> None:
        for field in fields:
            if field not in payload:
                raise ValueError(f"{label} missing required field: {field}")

    def _validate_memory_record_created_payload(self, payload: dict[str, Any]) -> None:
        self._require_fields(
            "memory.record_created",
            payload,
            ("record_id", "execution_id", "summary", "source_refs", "provenance", "basis_event_id"),
        )
        for field_name in ("content", "full_content", "artifact_content", "raw_content"):
            if field_name in payload:
                raise ValueError(f"memory.record_created cannot contain {field_name}")
        if not isinstance(payload["source_refs"], list):
            raise ValueError("memory.record_created source_refs must be a list")
        if not isinstance(payload["provenance"], dict):
            raise ValueError("memory.record_created provenance must be a dict")

    def _validate_memory_record_lifecycle(self, payload: dict[str, Any]) -> None:
        execution_id = str(payload["execution_id"])
        status = self._execution_statuses.get(execution_id)
        if status is None:
            outcomes = set(self._proposal_outcomes.values())
            if "denied" in outcomes:
                raise ValueError("memory.record_created after denied decision")
            if "pending_user_approval" in outcomes:
                raise ValueError("memory.record_created after pending decision")
            raise ValueError("memory.record_created requires completed write_memory execution")
        if status != "completed":
            raise ValueError(f"memory.record_created requires completed write_memory execution, got {status}")
        action_type = self._execution_action_types.get(execution_id)
        if action_type != "write_memory":
            raise ValueError("memory.record_created requires completed write_memory execution")

    def _validate_memory_record_superseded_payload(self, payload: dict[str, Any]) -> None:
        self._require_fields(
            "memory.record_superseded",
            payload,
            ("old_record_id", "new_record_id", "execution_id", "reason", "provenance", "basis_event_id"),
        )
        for field_name in ("content", "full_content", "artifact_content", "raw_content"):
            if field_name in payload:
                raise ValueError(f"memory.record_superseded cannot contain {field_name}")
        if not isinstance(payload["provenance"], dict):
            raise ValueError("memory.record_superseded provenance must be a dict")

    def _validate_memory_record_superseded_lifecycle(self, payload: dict[str, Any]) -> None:
        old_record_id = str(payload["old_record_id"])
        new_record_id = str(payload["new_record_id"])
        if old_record_id == new_record_id:
            raise ValueError("memory.record_superseded old_record_id and new_record_id must not be the same")
        if old_record_id not in self._memory_record_ids:
            raise ValueError("memory.record_superseded old_record_id must reference an existing record")
        if new_record_id not in self._memory_record_ids:
            raise ValueError("memory.record_superseded new_record_id must reference an existing record")

        execution_id = str(payload["execution_id"])
        status = self._execution_statuses.get(execution_id)
        if status is None:
            outcomes = set(self._proposal_outcomes.values())
            if "denied" in outcomes:
                raise ValueError("memory.record_superseded after denied decision")
            if "pending_user_approval" in outcomes:
                raise ValueError("memory.record_superseded after pending decision")
            raise ValueError("memory.record_superseded requires completed write_memory execution")
        if status != "completed":
            raise ValueError(f"memory.record_superseded requires completed write_memory execution, got {status}")
        action_type = self._execution_action_types.get(execution_id)
        if action_type != "write_memory":
            raise ValueError("memory.record_superseded requires completed write_memory execution")

    def apply(self, state: RunState, event: CanonicalEvent) -> None:
        state.last_event_id = event.event_id
        if not state.run_id:
            state.run_id = event.run_id

        payload = event.payload
        if event.event_type == "run.created":
            state.run_id = str(payload.get("run_id", event.run_id))
            state.status = "running"
        elif event.event_type == "agent.created":
            state.current_agent = str(payload.get("agent_id", ""))
        elif event.event_type == "action.started":
            execution_id = str(payload["execution_id"])
            state.actions[execution_id] = {
                "execution_id": execution_id,
                "proposal_id": payload.get("proposal_id"),
                "decision_id": payload.get("decision_id"),
                "status": "running",
            }
        elif event.event_type == "action.decided":
            outcome = str(payload.get("outcome", ""))
            if outcome in {"denied", "pending_user_approval"}:
                proposal_id = str(payload["proposal_id"])
                state.actions[proposal_id] = {
                    "proposal_id": proposal_id,
                    "decision_id": payload.get("decision_id"),
                    "status": outcome,
                }
                if outcome == "pending_user_approval":
                    state.status = "pending_user_approval"
        elif event.event_type == "approval.requested":
            proposal_id = str(payload["proposal_id"])
            action = state.actions.setdefault(proposal_id, {"proposal_id": proposal_id})
            action["decision_id"] = payload.get("decision_id")
            action["approval_id"] = payload.get("approval_id")
            action["status"] = "pending_user_approval"
            state.status = "pending_user_approval"
        elif event.event_type == "artifact.created":
            artifact = dict(payload["artifact"])
            state.artifacts.append(
                {
                    "ref": dict(artifact["ref"]),
                    "artifact_type": artifact["artifact_type"],
                    "summary": artifact["summary"],
                    "provenance": dict(artifact["provenance"]),
                }
            )
        elif event.event_type == "action.completed":
            execution_id = str(payload["execution_id"])
            action = state.actions.setdefault(execution_id, {"execution_id": execution_id})
            action["status"] = payload.get("status", "completed")
        elif event.event_type == "action.failed":
            execution_id = str(payload["execution_id"])
            action = state.actions.setdefault(execution_id, {"execution_id": execution_id})
            action["proposal_id"] = payload.get("proposal_id")
            action["decision_id"] = payload.get("decision_id")
            action["status"] = payload.get("status", "failed")
            state.status = "failed"
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
        elif event.event_type == "run.completed":
            state.status = str(payload.get("status", "completed"))

    def project(self, events: Iterable[CanonicalEvent]) -> RunState:
        self._proposal_outcomes = {}
        self._proposal_action_types = {}
        self._execution_statuses = {}
        self._execution_action_types = {}
        self._memory_record_ids = set()
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
            "created_at": datetime.now(timezone.utc).isoformat(),
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
        if not isinstance(state["actions"], dict):
            raise ValueError("checkpoint state actions must be a dict")
        if not isinstance(state["artifacts"], list):
            raise ValueError("checkpoint state artifacts must be a list")
        memory_records = state.get("memory_records", [])
        if not isinstance(memory_records, list):
            raise ValueError("checkpoint state memory_records must be a list")
        for artifact in state["artifacts"]:
            self._validate_checkpoint_artifact(artifact)
        for record in memory_records:
            self._validate_checkpoint_memory_record(record)
        return RunState(
            run_id=str(state.get("run_id", "")),
            status=str(state.get("status", "unknown")),
            current_agent=str(state.get("current_agent", "")),
            actions=dict(state.get("actions", {})),
            artifacts=list(state.get("artifacts", [])),
            memory_records=list(memory_records),
            last_event_id=str(state.get("last_event_id", "")),
        )

    def _validate_checkpoint_artifact(self, artifact: Any) -> None:
        if not isinstance(artifact, dict):
            raise ValueError("checkpoint artifact entry must be a dict")
        if "content" in artifact:
            raise ValueError("checkpoint artifact entry cannot contain content")
        for field in self.CHECKPOINT_ARTIFACT_FIELDS:
            if field not in artifact:
                raise ValueError(f"checkpoint artifact entry missing required field: {field}")

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
