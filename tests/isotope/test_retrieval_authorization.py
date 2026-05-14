import pytest

from isotope import artifact_store, refs, retrieval


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


def test_retrieval_rejects_missing_grants(tmp_path):
    artifact, service = _artifact_and_service(tmp_path)

    with pytest.raises(TypeError, match="grants must be a dict"):
        service.get_artifact_summary(artifact.ref, grants=None)


def test_retrieval_rejects_non_dict_grants(tmp_path):
    artifact, service = _artifact_and_service(tmp_path)

    with pytest.raises(TypeError, match="grants must be a dict"):
        service.get_artifact_summary(artifact.ref, grants=["artifact:summary"])


def test_retrieval_rejects_missing_artifact_grant(tmp_path):
    artifact, service = _artifact_and_service(tmp_path)

    with pytest.raises(PermissionError, match="artifact summary read is not granted"):
        service.get_artifact_summary(artifact.ref, grants={})


def test_retrieval_rejects_non_summary_read_grant(tmp_path):
    artifact, service = _artifact_and_service(tmp_path)

    with pytest.raises(PermissionError, match="artifact summary read is not granted"):
        service.get_artifact_summary(artifact.ref, grants={"artifact": {"read": "none"}})


def test_retrieval_rejects_full_content_grant_for_summary_api(tmp_path):
    artifact, service = _artifact_and_service(tmp_path)

    for read_grant in ("full", "content"):
        with pytest.raises(PermissionError, match="artifact summary read is not granted"):
            service.get_artifact_summary(artifact.ref, grants={"artifact": {"read": read_grant}})


def test_retrieval_summary_does_not_read_artifact_content(tmp_path, monkeypatch):
    artifact, service = _artifact_and_service(tmp_path)

    def fail_on_content_read(*args, **kwargs):
        raise AssertionError("summary retrieval must not read artifact content")

    monkeypatch.setattr(service.artifact_store, "get_content", fail_on_content_read)

    summary = service.get_artifact_summary(
        artifact.ref,
        grants={"artifact": {"read": "summary"}},
    )

    assert summary["summary"] == "hello artifact"


def test_retrieval_summary_response_excludes_content(tmp_path):
    artifact, service = _artifact_and_service(tmp_path)

    summary = service.get_artifact_summary(
        artifact.ref,
        grants={"artifact": {"read": "summary"}},
    )

    assert "content" not in summary


def test_retrieval_rejects_uri_string_ref(tmp_path):
    artifact, service = _artifact_and_service(tmp_path)

    with pytest.raises(TypeError, match="structured ResourceRef"):
        service.get_artifact_summary(
            f"artifact://run_001/{artifact.artifact_id}",
            grants={"artifact": {"read": "summary"}},
        )


def test_retrieval_rejects_non_artifact_resource_ref(tmp_path):
    _, service = _artifact_and_service(tmp_path)
    non_artifact_ref = refs.ResourceRef(
        ref_type="memory",
        scope="run",
        run_id="run_001",
        artifact_id="memory_001",
    )

    with pytest.raises(ValueError, match="artifact ResourceRef"):
        service.get_artifact_summary(
            non_artifact_ref,
            grants={"artifact": {"read": "summary"}},
        )
