"""Developer demo entrypoint for the Isotope v0.1 kernel slice."""

from __future__ import annotations

import argparse
import json
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .checkpoint_store import FileCheckpointStore
from .projector import RunProjector
from .server import InProcessServer


def run_demo(root_path: Path | str | None = None) -> dict[str, Any]:
    """Run the deterministic v0.1 kernel demo and return summary metadata."""

    if root_path is None:
        with tempfile.TemporaryDirectory(prefix="isotope-demo-") as temp_root:
            return _run_demo(Path(temp_root))
    return _run_demo(Path(root_path))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Isotope v0.1 kernel demo.")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    args = parser.parse_args(argv)

    result = run_demo()
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(_format_plain_text(result))
    return 0


def _run_demo(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    checkpoint_store = FileCheckpointStore(root)
    api = InProcessServer(root, checkpoint_store=checkpoint_store)

    session = api.create_session()
    run = api.create_run(session["session_id"], goal="demo deterministic artifact path")
    run_id = run["run_id"]
    api.submit_input(run_id, "hello")

    events = api.get_events(run_id)
    replay_state = RunProjector().rebuild(run_id, api.event_store)
    checkpoint = RunProjector().save_checkpoint(run_id, api.event_store, checkpoint_store)
    checkpoint_state = RunProjector().rebuild_with_checkpoint(run_id, api.event_store, checkpoint_store)
    artifacts = api.artifact_store.list_artifacts(run_id)
    artifact = artifacts[-1]

    artifact_ref = artifact.ref.to_dict()
    checkpoint_artifact_ref = (
        checkpoint_state.artifacts[0]["ref"] if checkpoint_state.artifacts else {}
    )
    replay_ok = asdict(replay_state) == asdict(api.get_run_state(run_id))
    checkpoint_ok = asdict(checkpoint_state) == asdict(replay_state)

    return {
        "session_id": session["session_id"],
        "run_id": run_id,
        "run_status": replay_state.status,
        "action_outcome": _latest_action_status(replay_state.actions),
        "artifact_ref": artifact_ref,
        "artifact_summary": artifact.summary,
        "event_count": len(events),
        "replay_ok": replay_ok,
        "checkpoint_ok": checkpoint_ok,
        "checkpoint_basis_event_id": checkpoint["basis_event_id"],
        "replay_run_status": replay_state.status,
        "checkpoint_run_status": checkpoint_state.status,
        "checkpoint_artifact_ref": checkpoint_artifact_ref,
        "memory_status": "boundary_only",
    }


def _latest_action_status(actions: dict[str, dict[str, Any]]) -> str:
    for action in reversed(list(actions.values())):
        status = action.get("status")
        if isinstance(status, str) and status:
            return status
    return "unknown"


def _format_plain_text(result: dict[str, Any]) -> str:
    lines = [
        f"session_id: {result['session_id']}",
        f"run_id: {result['run_id']}",
        f"run_status: {result['run_status']}",
        f"action_outcome: {result['action_outcome']}",
        f"artifact_ref: {json.dumps(result['artifact_ref'], sort_keys=True)}",
        f"artifact_summary: {result['artifact_summary']}",
        f"event_count: {result['event_count']}",
        f"replay_ok: {str(result['replay_ok']).lower()}",
        f"checkpoint_ok: {str(result['checkpoint_ok']).lower()}",
        f"memory_status: {result['memory_status']}",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
