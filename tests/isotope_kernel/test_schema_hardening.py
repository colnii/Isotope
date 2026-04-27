import pytest

from isotope_kernel import artifact_store, events, refs, retrieval


def _valid_event(**overrides):
    data = {
        "event_id": "evt_001",
        "run_id": "run_001",
        "event_type": "run.created",
        "payload": {"status": "running"},
        "created_at": "2026-04-27T00:00:00Z",
    }
    data.update(overrides)
    return data


@pytest.mark.parametrize("field", ["event_id", "run_id", "event_type", "created_at"])
def test_canonical_event_rejects_empty_required_string_fields(field):
    data = _valid_event(**{field: ""})

    with pytest.raises(ValueError):
        events.CanonicalEvent(**data)


def test_canonical_event_payload_must_be_dict():
    data = _valid_event(payload=["not", "a", "dict"])

    with pytest.raises(ValueError):
        events.CanonicalEvent(**data)


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"event_id": "evt_001"},
        _valid_event(payload=["not", "a", "dict"]),
    ],
)
def test_canonical_event_from_dict_rejects_missing_fields_or_non_dict_payload(data):
    with pytest.raises(ValueError):
        events.CanonicalEvent.from_dict(data)


@pytest.mark.parametrize(
    ("run_id", "artifact_id"),
    [
        ("", "artifact_001"),
        ("run_001", ""),
    ],
)
def test_make_artifact_ref_rejects_empty_ids(run_id, artifact_id):
    with pytest.raises(ValueError):
        refs.make_artifact_ref(run_id=run_id, artifact_id=artifact_id)


def test_retrieval_summary_rejects_non_artifact_ref(tmp_path):
    service = retrieval.RetrievalService(artifact_store.ArtifactStore(tmp_path))
    non_artifact_ref = refs.ResourceRef(
        ref_type="memory",
        scope="run",
        run_id="run_001",
        artifact_id="artifact_001",
    )

    with pytest.raises(ValueError):
        service.get_artifact_summary(
            non_artifact_ref,
            grants={"artifact": {"read": "summary"}},
        )


def test_retrieval_summary_still_rejects_uri_string(tmp_path):
    service = retrieval.RetrievalService(artifact_store.ArtifactStore(tmp_path))

    with pytest.raises(TypeError):
        service.get_artifact_summary(
            "artifact://run_001/artifact_001",
            grants={"artifact": {"read": "summary"}},
        )
