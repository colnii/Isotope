from __future__ import annotations

import inspect
from dataclasses import asdict
from typing import Any

import pytest

from isotope import demo, server
from isotope.checkpoint_store import FileCheckpointStore
from isotope.http_api import create_http_app
from isotope.projector import RunProjector


FORBIDDEN_CONTENT_KEYS = {
    "content",
    "artifact_content",
    "full_content",
    "full_text",
    "raw_content",
    "raw_artifact_content",
}


def _new_run(tmp_path):
    api = server.InProcessServer(tmp_path)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="source artifact helper")
    return api, run["run_id"]


def _create_source_artifact(api: server.InProcessServer, run_id: str) -> dict[str, Any]:
    return api.create_source_artifact(
        run_id,
        summary="source artifact summary",
        content="source artifact durable content",
    )


def _event_types(api: server.InProcessServer, run_id: str) -> list[str]:
    return [event.event_type for event in api.get_events(run_id)]


def _assert_no_forbidden_content_keys(value: Any) -> None:
    if isinstance(value, dict):
        forbidden = FORBIDDEN_CONTENT_KEYS.intersection(value)
        assert forbidden == set()
        for nested in value.values():
            _assert_no_forbidden_content_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_forbidden_content_keys(nested)


def test_source_artifact_helper_creates_summary_ref_and_provenance(tmp_path):
    api, run_id = _new_run(tmp_path)

    result = _create_source_artifact(api, run_id)

    artifact_ref = result["artifact_ref"]
    assert result["status"] == "completed"
    assert result["proposal_id"].startswith("prop_")
    assert result["decision_id"].startswith("dec_")
    assert result["execution_id"].startswith("exec_")
    assert result["artifact_summary"] == "source artifact summary"
    assert result["artifact_type"] == "text"
    assert artifact_ref.ref_type == "artifact"
    assert artifact_ref.scope == "run"
    assert artifact_ref.run_id == run_id
    assert artifact_ref.artifact_id.startswith("artifact_")
    assert result["provenance"] == {
        "execution_id": result["execution_id"],
        "proposal_id": result["proposal_id"],
        "decision_id": result["decision_id"],
    }


def test_source_artifact_helper_does_not_expose_full_content_in_returned_summary(tmp_path):
    api, run_id = _new_run(tmp_path)

    result = _create_source_artifact(api, run_id)

    public_shape = {
        key: value
        for key, value in result.items()
        if key != "run_state"
    }
    _assert_no_forbidden_content_keys(public_shape)
    assert "source artifact durable content" not in repr(public_shape)


def test_source_artifact_helper_appends_canonical_events_without_completing_run(tmp_path):
    api, run_id = _new_run(tmp_path)
    before_events = list(api.get_events(run_id))

    result = _create_source_artifact(api, run_id)

    after_events = list(api.get_events(run_id))
    assert len(after_events) == len(before_events) + 5
    assert _event_types(api, run_id) == [
        "run.created",
        "agent.created",
        "thread.created",
        "action.proposed",
        "action.decided",
        "action.started",
        "artifact.created",
        "action.completed",
    ]
    assert "run.completed" not in _event_types(api, run_id)
    assert result["run_state"].status == "running"


def test_source_artifact_helper_result_replays_into_run_state(tmp_path):
    api, run_id = _new_run(tmp_path)

    result = _create_source_artifact(api, run_id)
    replay_state = RunProjector().rebuild(run_id, api.event_store)

    assert asdict(replay_state) == asdict(api.get_run_state(run_id))
    assert replay_state.artifacts == [
        {
            "ref": result["artifact_ref"].to_dict(),
            "artifact_type": "text",
            "summary": "source artifact summary",
            "provenance": {
                "execution_id": result["execution_id"],
                "proposal_id": result["proposal_id"],
                "decision_id": result["decision_id"],
            },
        }
    ]


def test_source_artifact_helper_artifact_is_checkpoint_rebuildable(tmp_path):
    checkpoint_store = FileCheckpointStore(tmp_path / "checkpoints")
    api = server.InProcessServer(tmp_path, checkpoint_store=checkpoint_store)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="source checkpoint")
    run_id = run["run_id"]

    result = _create_source_artifact(api, run_id)
    RunProjector().save_checkpoint(run_id, api.event_store, checkpoint_store)
    checkpoint_state = RunProjector().rebuild_with_checkpoint(
        run_id,
        api.event_store,
        checkpoint_store,
    )

    assert result["artifact_ref"].to_dict() in [
        artifact["ref"] for artifact in checkpoint_state.artifacts
    ]
    assert "source artifact summary" in [
        artifact["summary"] for artifact in checkpoint_state.artifacts
    ]


def test_artifact_review_demo_uses_source_artifact_helper_not_private_append_glue():
    source = inspect.getsource(demo._run_artifact_review_spike)

    assert "create_source_artifact" in source
    assert "app.server._append(" not in source
    assert "source_proposal_id" not in source
    assert "source_decision_id" not in source
    assert "source_execution_id" not in source


def test_source_artifact_helper_does_not_open_http_full_content_route(tmp_path):
    app = create_http_app(tmp_path)
    session = app.server.create_session()
    run = app.server.create_run(session["session_id"], goal="source content route")

    result = app.server.create_source_artifact(
        run["run_id"],
        summary="source artifact summary",
        content="source artifact durable content",
    )
    response = app.request(
        "GET",
        f"/artifacts/{result['artifact_ref'].artifact_id}/content",
    )

    assert response.status_code == 501
    assert response.body["error"]["code"] == "not_enabled"


def test_source_artifact_helper_rejects_binary_or_file_like_inputs_without_artifact(tmp_path):
    api, run_id = _new_run(tmp_path)
    before_events = list(api.get_events(run_id))

    with pytest.raises(ValueError, match="content must be a non-empty string"):
        api.create_source_artifact(
            run_id,
            summary="source artifact summary",
            content=b"not text",
        )

    assert api.get_events(run_id) == before_events
    assert api.artifact_store.list_artifacts(run_id) == []


def test_malformed_source_artifact_setup_fails_fast_without_partial_artifact_state(tmp_path):
    api, run_id = _new_run(tmp_path)
    before_events = list(api.get_events(run_id))

    with pytest.raises(ValueError, match="summary must be a non-empty string"):
        api.create_source_artifact(
            run_id,
            summary="",
            content="source artifact durable content",
        )

    assert api.get_events(run_id) == before_events
    assert api.get_run_state(run_id).artifacts == []
    assert api.artifact_store.list_artifacts(run_id) == []
