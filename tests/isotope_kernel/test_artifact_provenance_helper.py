from __future__ import annotations

from typing import Any

import pytest

from isotope_kernel.http_api import create_http_app
from isotope_kernel.refs import make_artifact_ref
from isotope_kernel.server import InProcessServer


FORBIDDEN_CONTENT_KEYS = {
    "content",
    "artifact_content",
    "full_content",
    "full_text",
    "raw_content",
    "raw_artifact_content",
}


def _new_run(tmp_path):
    api = InProcessServer(tmp_path)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="artifact provenance helper")
    return api, run["run_id"]


def _source_artifact(api: InProcessServer, run_id: str) -> dict[str, Any]:
    return api.create_source_artifact(
        run_id,
        summary="source artifact summary",
        content="source artifact durable content",
    )


def _assert_no_forbidden_content_keys(value: Any) -> None:
    if isinstance(value, dict):
        assert FORBIDDEN_CONTENT_KEYS.intersection(value) == set()
        for nested in value.values():
            _assert_no_forbidden_content_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_forbidden_content_keys(nested)


def test_get_artifact_record_returns_summary_ref_provenance_and_basis_metadata(tmp_path):
    api, run_id = _new_run(tmp_path)
    source = _source_artifact(api, run_id)

    record = api.get_artifact_record(source["artifact_ref"])

    assert record["artifact_id"] == source["artifact_ref"].artifact_id
    assert record["artifact_type"] == "text"
    assert record["summary"] == "source artifact summary"
    assert record["ref"] == source["artifact_ref"].to_dict()
    assert record["provenance"] == {"execution_id": source["execution_id"]}
    assert record["basis_event_id"].startswith("evt_")
    assert record["basis_event_type"] == "artifact.created"
    assert record["basis_created_at"] == "2026-04-27T00:00:00Z"


def test_get_artifact_record_requires_structured_resource_ref(tmp_path):
    api, run_id = _new_run(tmp_path)
    source = _source_artifact(api, run_id)

    with pytest.raises(TypeError, match="structured ResourceRef"):
        api.get_artifact_record(f"artifact://{source['artifact_ref'].artifact_id}")
    with pytest.raises(TypeError, match="structured ResourceRef"):
        api.get_artifact_record(source["artifact_ref"].artifact_id)


def test_get_artifact_record_rejects_unknown_or_wrong_ref(tmp_path):
    api, run_id = _new_run(tmp_path)
    unknown_ref = make_artifact_ref(run_id=run_id, artifact_id="artifact_missing")
    wrong_type_ref = make_artifact_ref(run_id=run_id, artifact_id="artifact_001")
    object.__setattr__(wrong_type_ref, "ref_type", "memory")

    with pytest.raises(FileNotFoundError, match="artifact not found"):
        api.get_artifact_record(unknown_ref)
    with pytest.raises(ValueError, match="artifact ResourceRef"):
        api.get_artifact_record(wrong_type_ref)


def test_get_artifact_record_does_not_return_full_content_or_append_events(tmp_path):
    api, run_id = _new_run(tmp_path)
    source = _source_artifact(api, run_id)
    before_events = list(api.get_events(run_id))

    record = api.get_artifact_record(source["artifact_ref"])

    _assert_no_forbidden_content_keys(record)
    assert "source artifact durable content" not in repr(record)
    assert api.get_events(run_id) == before_events


def test_get_artifact_record_does_not_open_http_full_content_route(tmp_path):
    app = create_http_app(tmp_path)
    session = app.server.create_session()
    run = app.server.create_run(session["session_id"], goal="artifact route still deferred")
    source = app.server.create_source_artifact(
        run["run_id"],
        summary="source artifact summary",
        content="source artifact durable content",
    )

    record = app.server.get_artifact_record(source["artifact_ref"])
    response = app.request("GET", f"/artifacts/{record['artifact_id']}/content")

    assert response.status_code == 501
    assert response.body["error"]["code"] == "not_enabled"
