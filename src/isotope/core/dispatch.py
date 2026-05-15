"""Thin dispatch layer from product core to the in-process runtime."""

from __future__ import annotations

from typing import Any

from .response import CoreTurnResponse
from .session import CoreRun, CoreSession


class RuntimeDispatch:
    """Delegate product core calls to the current single-process runtime."""

    def __init__(self, runtime: Any):
        self.runtime = runtime

    def start_session(self) -> CoreSession:
        session = self.runtime.create_session()
        return CoreSession(session_id=session["session_id"])

    def start_run(self, session_id: str, *, goal: str) -> CoreRun:
        run = self.runtime.create_run(session_id, goal=goal)
        return CoreRun(run_id=run["run_id"], session_id=session_id, goal=goal)

    def submit_user_message(self, run_id: str, text: str) -> CoreTurnResponse:
        result = self.runtime.submit_input(run_id, text)
        run_state = result["run_state"]
        artifact = run_state.artifacts[-1] if run_state.artifacts else {}
        artifact_ref = result.get("artifact_ref")
        if hasattr(artifact_ref, "to_dict"):
            artifact_ref = artifact_ref.to_dict()
        if not isinstance(artifact_ref, dict):
            artifact_ref = dict(artifact.get("ref", {}))
        return CoreTurnResponse(
            status=str(result["status"]),
            run_id=run_id,
            run_status=str(run_state.status),
            artifact_ref=dict(artifact_ref),
            artifact_summary=str(artifact.get("summary", "")),
            event_count=len(self.runtime.get_events(run_id)),
        )
