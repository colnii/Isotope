"""Artifact-review developer demo scenario."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from .demo_common import _deferred_status
from .interfaces.http import create_http_app
from .platform.state.checkpoint_store import FileCheckpointStore
from .platform.state.projector import RunProjector


def _run_artifact_review_spike(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    app = create_http_app(root)

    session_response = app.request("POST", "/sessions", {})
    session_id = session_response.body["session_id"]  # type: ignore[index]
    run_response = app.request(
        "POST",
        f"/sessions/{session_id}/runs",
        {"goal": "artifact review flow spike"},
    )
    run_id = run_response.body["run_id"]  # type: ignore[index]

    source_setup = app.server.create_source_artifact(
        run_id,
        summary="source artifact summary",
        content="source artifact durable content",
    )
    source_artifact_ref = source_setup["artifact_ref"]
    source_record = app.server.get_artifact_record(source_artifact_ref)

    source_summary = app.server.retrieval.get_artifact_summary(
        source_artifact_ref,
        {"artifact": {"read": "summary"}},
    )
    controlled_retrieval = app.server.retrieval.get_artifact_content(
        source_artifact_ref,
        grants={"artifact": {"read": "full"}},
        caller_context={
            "caller": "artifact_review_demo",
            "run_id": run_id,
            "source_artifact_id": source_record["artifact_id"],
        },
        purpose="artifact_review_flow",
    )
    summary_only_ok = "content" not in source_summary and source_summary["ref"] == source_artifact_ref.to_dict()
    controlled_retrieval_ok = (
        controlled_retrieval.get("status") == "ok"
        and controlled_retrieval.get("view") == "full"
        and isinstance(controlled_retrieval.get("content"), str)
    )

    review_result = app.server.submit_action(
        run_id,
        {
            "action": "call_tool",
            "tool": "write_artifact_tool",
            "text": "review artifact durable content: accepted source artifact",
        },
    )
    review_artifact_ref = review_result["artifact_ref"].to_dict()
    review_artifact = app.server.artifact_store.list_artifacts(run_id)[-1]

    state_response = app.request("GET", f"/runs/{run_id}")
    events_response = app.request("GET", f"/runs/{run_id}/events")
    source_summary_response = app.request(
        "GET",
        f"/artifacts/{source_record['artifact_id']}/summary",
    )
    review_summary_response = app.request(
        "GET",
        f"/artifacts/{review_artifact.artifact_id}/summary",
    )
    http_full_content_response = app.request(
        "GET",
        f"/artifacts/{source_record['artifact_id']}/content",
    )

    replay_state = RunProjector().rebuild(run_id, app.server.event_store)
    checkpoint_store = FileCheckpointStore(root / "artifact-review-checkpoints")
    checkpoint = RunProjector().save_checkpoint(run_id, app.server.event_store, checkpoint_store)
    checkpoint_state = RunProjector().rebuild_with_checkpoint(
        run_id,
        app.server.event_store,
        checkpoint_store,
    )
    final_state = app.server.get_run_state(run_id)
    event_types = [event.event_type for event in app.server.get_events(run_id)]
    replay_artifacts = list(replay_state.artifacts)
    checkpoint_artifacts = list(checkpoint_state.artifacts)
    replay_artifact_refs = [artifact["ref"] for artifact in replay_artifacts]
    checkpoint_artifact_refs = [artifact["ref"] for artifact in checkpoint_artifacts]
    replay_artifact_summaries = [artifact["summary"] for artifact in replay_artifacts]
    checkpoint_artifact_summaries = [artifact["summary"] for artifact in checkpoint_artifacts]
    review_artifact_state = next(
        artifact for artifact in replay_artifacts if artifact["ref"] == review_artifact_ref
    )
    review_decision = {
        "status": "accepted",
        "source_ref": source_artifact_ref.to_dict(),
        "basis_summary": source_summary["summary"],
        "review_artifact_ref": review_artifact_ref,
        "provenance": {
            "source_ref": source_artifact_ref.to_dict(),
            "source_basis_event_id": source_record["basis_event_id"],
            "review_artifact_ref": review_artifact_ref,
            "review_execution_id": review_result["execution_id"],
        },
    }
    review_action_chain_ok = (
        event_types.count("action.proposed") >= 1
        and event_types.count("action.decided") >= 1
        and event_types.count("action.started") >= 1
        and event_types.count("action.completed") >= 1
        and event_types.count("artifact.created") >= 2
        and review_artifact_ref in replay_artifact_refs
    )
    replay_ok = asdict(replay_state) == asdict(final_state)
    checkpoint_ok = asdict(checkpoint_state) == asdict(replay_state)
    content_policy_ok = (
        summary_only_ok
        and controlled_retrieval_ok
        and _deferred_status(http_full_content_response) == "not_enabled"
    )
    http_api_ok = (
        session_response.status_code == 201
        and run_response.status_code == 201
        and state_response.status_code == 200
        and events_response.status_code == 200
        and source_summary_response.status_code == 200
        and review_summary_response.status_code == 200
    )

    return {
        "scenario": "artifact-review",
        "session_id": session_id,
        "run_id": run_id,
        "run_status": replay_state.status,
        "transport": "in_process",
        "http_api_ok": http_api_ok,
        "review_ok": (
            review_action_chain_ok
            and content_policy_ok
            and replay_ok
            and checkpoint_ok
            and replay_state.status == "completed"
        ),
        "artifact_ref": source_artifact_ref.to_dict(),
        "review_artifact_ref": review_artifact_ref,
        "source_summary": source_summary,
        "source_artifact_record": source_record,
        "source_setup": {
            "status": source_setup["status"],
            "proposal_id": source_setup["proposal_id"],
            "decision_id": source_setup["decision_id"],
            "execution_id": source_setup["execution_id"],
            "artifact_ref": source_setup["artifact_ref"].to_dict(),
            "artifact_summary": source_setup["artifact_summary"],
            "artifact_type": source_setup["artifact_type"],
            "provenance": dict(source_setup["provenance"]),
        },
        "review_summary": review_artifact.summary,
        "review_decision": review_decision,
        "review_artifact_provenance": dict(review_artifact_state["provenance"]),
        "review_action_chain_ok": review_action_chain_ok,
        "summary_only_ok": summary_only_ok,
        "content_policy_ok": content_policy_ok,
        "controlled_retrieval_ok": controlled_retrieval_ok,
        "controlled_retrieval_view": controlled_retrieval.get("view"),
        "replay_ok": replay_ok,
        "checkpoint_ok": checkpoint_ok,
        "checkpoint_basis_event_id": checkpoint["basis_event_id"],
        "replay_artifacts": replay_artifacts,
        "checkpoint_artifacts": checkpoint_artifacts,
        "replay_artifact_refs": replay_artifact_refs,
        "checkpoint_artifact_refs": checkpoint_artifact_refs,
        "replay_artifact_summaries": replay_artifact_summaries,
        "checkpoint_artifact_summaries": checkpoint_artifact_summaries,
        "event_count": len(event_types),
        "event_types": event_types,
        "http_full_content_route_status": _deferred_status(http_full_content_response),
        "filesystem_mutation_status": "not_used",
        "network_listener_status": "not_used",
        "model_status": "not_used",
        "semantic_retrieval_status": "not_used",
        "ranking_status": "not_used",
        "memory_status": "boundary_only",
        "memory_query_status": "not_enabled",
    }


__all__ = ["_run_artifact_review_spike"]
