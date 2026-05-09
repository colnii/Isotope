import pytest

from isotope_kernel import artifact_store, event_store, events, projector, refs, retrieval


ARTIFACT_REF = {
    "ref_type": "artifact",
    "scope": "run",
    "run_id": "run_001",
    "artifact_id": "artifact_001",
}

FORBIDDEN_CONTENT_KEYS = {
    "content",
    "artifact_content",
    "full_content",
    "full_text",
    "raw_content",
    "raw_artifact_content",
}


def _artifact_and_service(tmp_path):
    store = artifact_store.ArtifactStore(tmp_path)
    artifact = store.create_artifact(
        run_id="run_001",
        execution_id="exec_001",
        artifact_type="text",
        summary="hello artifact",
        content="hidden durable content",
    )
    return artifact, retrieval.RetrievalService(store)


def _caller_context():
    return {
        "caller": "test_http_api",
        "run_id": "run_001",
        "purpose": "developer_demo",
    }


def _full_content_grants():
    return {"artifact": {"read": "full"}}


def _summary_grants():
    return {"artifact": {"read": "summary"}}


def _event(event_id, event_type, payload):
    return events.CanonicalEvent(
        event_id=event_id,
        run_id="run_001",
        event_type=event_type,
        payload=payload,
        created_at=f"2026-05-01T00:00:{event_id[-2:]}Z",
    )


def _canonical_events():
    return [
        _event("evt_001", "run.created", {"run_id": "run_001"}),
        _event("evt_002", "agent.created", {"agent_id": "agent_supervisor"}),
        _event(
            "evt_003",
            "action.proposed",
            {
                "proposal_id": "prop_001",
                "agent_id": "agent_supervisor",
                "action_type": "call_tool",
                "registry_id": "default",
                "registry_version": "v0.2",
            },
        ),
        _event(
            "evt_004",
            "action.decided",
            {
                "decision_id": "dec_001",
                "proposal_id": "prop_001",
                "outcome": "approved",
                "policy_profile_id": "default",
                "policy_version": "v0.2",
            },
        ),
        _event(
            "evt_005",
            "action.started",
            {
                "execution_id": "exec_001",
                "proposal_id": "prop_001",
                "decision_id": "dec_001",
            },
        ),
        _event(
            "evt_006",
            "artifact.created",
            {
                "artifact": {
                    "ref": ARTIFACT_REF,
                    "artifact_type": "text",
                    "summary": "hello artifact",
                    "provenance": {"execution_id": "exec_001", "proposal_id": "prop_001", "decision_id": "dec_001"},
                }
            },
        ),
        _event(
            "evt_007",
            "action.completed",
            {
                "execution_id": "exec_001",
                "status": "completed",
                "artifact_refs": [ARTIFACT_REF],
            },
        ),
        _event("evt_008", "run.completed", {"status": "completed"}),
    ]


def test_retrieval_summary_returns_ref_summary_and_provenance_without_content(tmp_path):
    artifact, service = _artifact_and_service(tmp_path)

    summary = service.get_artifact_summary(artifact.ref, grants=_summary_grants())

    assert summary["ref"] == artifact.ref.to_dict()
    assert summary["summary"] == "hello artifact"
    assert summary["provenance"] == {"execution_id": "exec_001"}
    assert FORBIDDEN_CONTENT_KEYS.isdisjoint(summary)


@pytest.mark.parametrize(
    "bad_ref_factory",
    [
        lambda artifact: f"artifact://run_001/{artifact.artifact_id}",
        lambda artifact: artifact.artifact_id,
    ],
)
def test_full_content_retrieval_requires_structured_resource_ref(tmp_path, bad_ref_factory):
    artifact, service = _artifact_and_service(tmp_path)

    with pytest.raises((TypeError, ValueError), match="ResourceRef|ref"):
        service.get_artifact_content(
            bad_ref_factory(artifact),
            grants=_full_content_grants(),
            caller_context=_caller_context(),
            purpose="developer_demo",
        )


def test_full_content_retrieval_requires_grants(tmp_path):
    artifact, service = _artifact_and_service(tmp_path)

    with pytest.raises((TypeError, PermissionError, ValueError), match="grant"):
        service.get_artifact_content(
            artifact.ref,
            grants=None,
            caller_context=_caller_context(),
            purpose="developer_demo",
        )


@pytest.mark.parametrize("caller_context", [None, {}, "not a dict"])
def test_full_content_retrieval_requires_caller_context(tmp_path, caller_context):
    artifact, service = _artifact_and_service(tmp_path)

    with pytest.raises((TypeError, PermissionError, ValueError), match="caller|context|purpose"):
        service.get_artifact_content(
            artifact.ref,
            grants=_full_content_grants(),
            caller_context=caller_context,
            purpose="developer_demo",
        )


def test_full_content_retrieval_requires_purpose(tmp_path):
    artifact, service = _artifact_and_service(tmp_path)

    with pytest.raises((TypeError, PermissionError, ValueError), match="purpose"):
        service.get_artifact_content(
            artifact.ref,
            grants=_full_content_grants(),
            caller_context=_caller_context(),
            purpose="",
        )


def test_summary_grant_cannot_read_full_content(tmp_path, monkeypatch):
    artifact, service = _artifact_and_service(tmp_path)

    def fail_on_content_read(*args, **kwargs):
        raise AssertionError("unauthorized full-content retrieval must not read content")

    monkeypatch.setattr(service.artifact_store, "get_content", fail_on_content_read)

    try:
        result = service.get_artifact_content(
            artifact.ref,
            grants=_summary_grants(),
            caller_context=_caller_context(),
            purpose="developer_demo",
        )
    except PermissionError as exc:
        assert "content" in str(exc) or "grant" in str(exc)
    else:
        assert result["status"] in {"limited", "denied"}
        assert result.get("view") in {"summary", None}
        assert FORBIDDEN_CONTENT_KEYS.isdisjoint(result)


def test_full_content_grant_allows_content(tmp_path):
    artifact, service = _artifact_and_service(tmp_path)

    result = service.get_artifact_content(
        artifact.ref,
        grants=_full_content_grants(),
        caller_context=_caller_context(),
        purpose="developer_demo",
    )

    assert result["status"] == "ok"
    assert result["view"] == "full"
    assert result["ref"] == artifact.ref.to_dict()
    assert result["summary"] == "hello artifact"
    assert result["content"] == "hidden durable content"
    assert result["provenance"] == {"execution_id": "exec_001"}


def test_full_content_retrieval_rejects_wrong_ref_type(tmp_path):
    _, service = _artifact_and_service(tmp_path)
    memory_ref = refs.ResourceRef(
        ref_type="memory",
        scope="run",
        run_id="run_001",
        artifact_id="memory_001",
    )

    with pytest.raises(ValueError, match="artifact ResourceRef|ref_type"):
        service.get_artifact_content(
            memory_ref,
            grants=_full_content_grants(),
            caller_context=_caller_context(),
            purpose="developer_demo",
        )


def test_full_content_retrieval_missing_artifact_is_controlled(tmp_path):
    _, service = _artifact_and_service(tmp_path)
    missing_ref = refs.make_artifact_ref(run_id="run_001", artifact_id="artifact_missing")

    with pytest.raises((FileNotFoundError, PermissionError, ValueError), match="artifact"):
        service.get_artifact_content(
            missing_ref,
            grants=_full_content_grants(),
            caller_context=_caller_context(),
            purpose="developer_demo",
        )


def test_content_read_does_not_append_events_or_change_run_state(tmp_path):
    artifact, service = _artifact_and_service(tmp_path)
    store = event_store.FileEventStore(tmp_path)
    for event in _canonical_events():
        store.append(event)
    before_events = store.list_events("run_001")
    before_state = projector.RunProjector().rebuild("run_001", store)

    service.get_artifact_content(
        artifact.ref,
        grants=_full_content_grants(),
        caller_context=_caller_context(),
        purpose="developer_demo",
    )

    after_events = store.list_events("run_001")
    after_state = projector.RunProjector().rebuild("run_001", store)

    assert after_events == before_events
    assert after_state == before_state


def test_projector_still_does_not_read_artifact_content(monkeypatch):
    def fail_on_content_read(*args, **kwargs):
        raise AssertionError("Projector must not read artifact content")

    monkeypatch.setattr(artifact_store.ArtifactStore, "get_content", fail_on_content_read)

    state = projector.RunProjector().project(_canonical_events())

    assert state.artifacts[0]["summary"] == "hello artifact"
    assert FORBIDDEN_CONTENT_KEYS.isdisjoint(state.artifacts[0])
