"""RunState projector boundary for the Isotope v0.1 slice."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

from .events import CanonicalEvent


@dataclass
class RunState:
    """In-memory read model for the v0.1 slice, not a source of truth."""

    run_id: str = ""
    status: str = "unknown"
    current_agent: str = ""
    actions: dict[str, dict[str, Any]] = field(default_factory=dict)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    last_event_id: str = ""


class RunProjector:
    """Project RunState only from canonical events."""

    EXECUTABLE_DECISION_OUTCOMES = {"approved", "modified"}
    KNOWN_DECISION_OUTCOMES = {"approved", "modified", "denied", "pending_user_approval"}
    KNOWN_RUN_STATUSES = {"unknown", "running", "pending_user_approval", "failed", "completed"}
    CHECKPOINT_STATE_FIELDS = ("run_id", "status", "current_agent", "actions", "artifacts", "last_event_id")
    CHECKPOINT_ARTIFACT_FIELDS = ("ref", "artifact_type", "summary", "provenance")
    PROJECTOR_VERSION = "run_projector@v1"

    def __init__(self) -> None:
        self._proposal_outcomes: dict[str, str] = {}
        self._execution_statuses: dict[str, str] = {}
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
        }:
            raise ValueError("event after run.completed")

        if event.event_type == "action.decided":
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

    def _require_fields(self, label: str, payload: dict[str, Any], fields: tuple[str, ...]) -> None:
        for field in fields:
            if field not in payload:
                raise ValueError(f"{label} missing required field: {field}")

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
        elif event.event_type == "run.completed":
            state.status = str(payload.get("status", "completed"))

    def project(self, events: Iterable[CanonicalEvent]) -> RunState:
        self._proposal_outcomes = {}
        self._execution_statuses = {}
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
            "state": asdict(state),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        checkpoint["integrity"] = {
            "algorithm": "sha256",
            "checkpoint_hash": self._checkpoint_hash(self._checkpoint_payload_for_hash(checkpoint)),
            "event_digest_algorithm": "sha256",
            "event_prefix_digest": self._event_prefix_digest(canonical_events),
            "event_digest_basis_event_id": checkpoint["basis_event_id"],
            "event_digest_event_count": len(canonical_events),
        }
        return checkpoint

    def rebuild_with_checkpoint(
        self,
        run_id: str,
        event_store,
        checkpoint_store,
        projector_version: str = PROJECTOR_VERSION,
    ) -> RunState:
        checkpoint = checkpoint_store.load_latest_checkpoint(run_id)
        if checkpoint is None:
            return self.rebuild(run_id, event_store)
        if not self._is_compatible_projector_version(checkpoint, projector_version):
            return self.rebuild(run_id, event_store)
        if checkpoint["run_id"] != run_id:
            raise ValueError("checkpoint run_id must match rebuild run_id")
        if not self._validate_checkpoint_integrity(checkpoint):
            return self.rebuild(run_id, event_store)

        canonical_events = event_store.list_events(run_id)
        basis_index = self._find_basis_index(canonical_events, checkpoint["basis_event_id"])
        if not self._validate_event_prefix_digest(checkpoint, canonical_events, basis_index):
            return self.rebuild(run_id, event_store)

        # Validate prefix from canonical events before trusting the checkpoint state.
        prefix_state = self.project(canonical_events[: basis_index + 1])
        state = self._run_state_from_checkpoint(checkpoint["state"], run_id, checkpoint["basis_event_id"])
        if state != prefix_state:
            return self.rebuild(run_id, event_store)

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
        for field in self.CHECKPOINT_STATE_FIELDS:
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
        for artifact in state["artifacts"]:
            self._validate_checkpoint_artifact(artifact)
        return RunState(
            run_id=str(state.get("run_id", "")),
            status=str(state.get("status", "unknown")),
            current_agent=str(state.get("current_agent", "")),
            actions=dict(state.get("actions", {})),
            artifacts=list(state.get("artifacts", [])),
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
