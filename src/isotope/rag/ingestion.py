"""External ingestion service for structured provider input."""

from __future__ import annotations

import json
from typing import Any


INGESTION_RESULT_STATUSES = (
    "canonical_event",
    "imported_snapshot",
    "artifact_only",
    "rejected",
)


class ExternalIngestionService:
    """Capture structured provider input as run artifacts."""

    def __init__(self, *, event_store, artifact_store):
        self.event_store = event_store
        self.artifact_store = artifact_store

    def ingest_raw(self, run_id: str, raw_input: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(run_id, str) or not run_id:
            raise ValueError("run_id must be a non-empty string")
        if not self._is_structured_raw_input(raw_input):
            return {
                "status": "rejected",
                "reason": "malformed external input",
            }

        artifact = self.artifact_store.create_artifact(
            run_id=run_id,
            execution_id="external_ingestion_boundary",
            artifact_type="external_raw_input",
            summary=f"External input from {raw_input['source_system']}",
            content=json.dumps(raw_input, sort_keys=True),
        )
        return {
            "status": "artifact_only",
            "artifact_ref": artifact.ref.to_dict(),
            "raw_artifact_ref": artifact.ref.to_dict(),
        }

    def _is_structured_raw_input(self, raw_input: object) -> bool:
        if not isinstance(raw_input, dict):
            return False
        source_system = raw_input.get("source_system")
        captured_at = raw_input.get("captured_at")
        body = raw_input.get("body")
        return (
            isinstance(source_system, str)
            and bool(source_system)
            and isinstance(captured_at, str)
            and bool(captured_at)
            and isinstance(body, dict)
        )
