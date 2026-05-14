import pytest

from isotope import artifact_store, refs


def _create_artifact(tmp_path):
    store = artifact_store.ArtifactStore(tmp_path)
    artifact = store.create_artifact(
        run_id="run_001",
        execution_id="exec_001",
        artifact_type="text",
        summary="hello artifact",
        content="hello durable content",
    )
    return artifact


def _artifact_path(tmp_path, artifact):
    return tmp_path / "runs" / artifact.run_id / "artifacts" / f"{artifact.artifact_id}.json"


def test_fresh_artifact_store_reads_persisted_metadata_by_ref(tmp_path):
    artifact = _create_artifact(tmp_path)
    fresh_store = artifact_store.ArtifactStore(tmp_path)

    metadata = fresh_store.get_metadata(artifact.ref)

    assert metadata == {
        "artifact_id": artifact.artifact_id,
        "artifact_type": "text",
        "summary": "hello artifact",
    }


def test_fresh_artifact_store_reads_persisted_content_by_ref(tmp_path):
    artifact = _create_artifact(tmp_path)
    fresh_store = artifact_store.ArtifactStore(tmp_path)

    content = fresh_store.get_content(artifact.ref)

    assert content == "hello durable content"


def test_fresh_artifact_store_lists_persisted_run_artifacts(tmp_path):
    artifact = _create_artifact(tmp_path)
    fresh_store = artifact_store.ArtifactStore(tmp_path)

    listed = fresh_store.list_artifacts("run_001")

    assert [item.artifact_id for item in listed] == [artifact.artifact_id]
    assert listed[0].ref == artifact.ref
    assert listed[0].content == "hello durable content"


def test_artifact_store_rejects_uri_string_ref(tmp_path):
    artifact = _create_artifact(tmp_path)
    store = artifact_store.ArtifactStore(tmp_path)
    uri = f"artifact://run_001/{artifact.artifact_id}"

    with pytest.raises(TypeError, match="structured ResourceRef or artifact_id"):
        store.get_metadata(uri)
    with pytest.raises(TypeError, match="structured ResourceRef or artifact_id"):
        store.get_content(uri)


def test_artifact_store_missing_ref_fails(tmp_path):
    store = artifact_store.ArtifactStore(tmp_path)
    missing_ref = refs.make_artifact_ref(run_id="run_001", artifact_id="artifact_missing")

    with pytest.raises(FileNotFoundError, match="artifact not found"):
        store.get_metadata(missing_ref)
    with pytest.raises(FileNotFoundError, match="artifact not found"):
        store.get_content(missing_ref)


def test_artifact_store_malformed_file_fails_fast(tmp_path):
    artifact = _create_artifact(tmp_path)
    _artifact_path(tmp_path, artifact).write_text("{not-json", encoding="utf-8")
    fresh_store = artifact_store.ArtifactStore(tmp_path)

    with pytest.raises(ValueError, match="malformed artifact file"):
        fresh_store.get_metadata(artifact.ref)
