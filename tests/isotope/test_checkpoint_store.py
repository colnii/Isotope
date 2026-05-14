import json

import pytest

from isotope import checkpoint_store


def _checkpoint(run_id="run_001", state=None):
    return {
        "run_id": run_id,
        "projector_version": "projector-v0.1",
        "basis_event_id": "evt_123",
        "state": state or {"status": "completed"},
        "created_at": "2026-04-28T00:00:00Z",
    }


def test_file_checkpoint_store_exists():
    assert hasattr(checkpoint_store, "FileCheckpointStore")


def test_save_and_load_latest_checkpoint_round_trips_opaque_blob(tmp_path):
    store = checkpoint_store.FileCheckpointStore(tmp_path)
    checkpoint = _checkpoint(state={"status": "nonsense_but_opaque", "actions": {"exec_001": "opaque"}})

    store.save_checkpoint("run_001", checkpoint)

    assert store.load_latest_checkpoint("run_001") == checkpoint


def test_checkpoint_file_path_is_run_scoped(tmp_path):
    store = checkpoint_store.FileCheckpointStore(tmp_path)

    store.save_checkpoint("run_001", _checkpoint())

    assert (tmp_path / "runs" / "run_001" / "checkpoints" / "latest.json").exists()


def test_missing_checkpoint_returns_none(tmp_path):
    store = checkpoint_store.FileCheckpointStore(tmp_path)

    assert store.load_latest_checkpoint("run_missing") is None


def test_checkpoint_must_be_dict(tmp_path):
    store = checkpoint_store.FileCheckpointStore(tmp_path)

    with pytest.raises(TypeError, match="checkpoint must be a dict"):
        store.save_checkpoint("run_001", ["not", "a", "dict"])


@pytest.mark.parametrize(
    "missing_field",
    ["run_id", "projector_version", "basis_event_id", "state", "created_at"],
)
def test_checkpoint_requires_minimal_fields(tmp_path, missing_field):
    store = checkpoint_store.FileCheckpointStore(tmp_path)
    checkpoint = _checkpoint()
    checkpoint.pop(missing_field)

    with pytest.raises(ValueError, match=f"checkpoint missing required field: {missing_field}"):
        store.save_checkpoint("run_001", checkpoint)


def test_checkpoint_run_id_must_match_save_run_id(tmp_path):
    store = checkpoint_store.FileCheckpointStore(tmp_path)

    with pytest.raises(ValueError, match="checkpoint run_id must match save run_id"):
        store.save_checkpoint("run_001", _checkpoint(run_id="run_002"))


@pytest.mark.parametrize("forbidden_key", ["raw_input", "provider_response", "imported_snapshot"])
def test_checkpoint_rejects_external_raw_input_keys(tmp_path, forbidden_key):
    store = checkpoint_store.FileCheckpointStore(tmp_path)
    checkpoint = _checkpoint()
    checkpoint[forbidden_key] = {"raw": "not allowed"}

    with pytest.raises(ValueError, match=f"checkpoint cannot contain external raw input: {forbidden_key}"):
        store.save_checkpoint("run_001", checkpoint)


def test_malformed_checkpoint_file_fails_fast(tmp_path):
    store = checkpoint_store.FileCheckpointStore(tmp_path)
    path = tmp_path / "runs" / "run_001" / "checkpoints" / "latest.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(ValueError, match="malformed checkpoint file"):
        store.load_latest_checkpoint("run_001")


def test_checkpoint_store_does_not_modify_event_log(tmp_path):
    store = checkpoint_store.FileCheckpointStore(tmp_path)
    event_log = tmp_path / "runs" / "run_001" / "events.jsonl"
    event_log.parent.mkdir(parents=True)
    event_log.write_text('{"event_id":"evt_001"}\n', encoding="utf-8")

    before = event_log.read_text(encoding="utf-8")
    store.save_checkpoint("run_001", _checkpoint())
    after = event_log.read_text(encoding="utf-8")

    assert after == before


def test_checkpoint_store_does_not_create_event_log(tmp_path):
    store = checkpoint_store.FileCheckpointStore(tmp_path)
    event_log = tmp_path / "runs" / "run_001" / "events.jsonl"

    store.save_checkpoint("run_001", _checkpoint())

    assert not event_log.exists()


def test_checkpoint_file_contains_json_object(tmp_path):
    store = checkpoint_store.FileCheckpointStore(tmp_path)
    checkpoint = _checkpoint()

    store.save_checkpoint("run_001", checkpoint)

    data = json.loads((tmp_path / "runs" / "run_001" / "checkpoints" / "latest.json").read_text())
    assert data == checkpoint
