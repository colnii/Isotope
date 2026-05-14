import json

import pytest

from isotope import checkpoint_store


def _checkpoint(
    run_id="run_001",
    basis_event_id="evt_001",
    created_at="2026-04-28T00:00:01Z",
    state=None,
):
    return {
        "run_id": run_id,
        "projector_version": "run_projector@v1",
        "basis_event_id": basis_event_id,
        "state": state or {"status": "opaque"},
        "created_at": created_at,
    }


def _event_log_path(root, run_id="run_001"):
    return root / "runs" / run_id / "events.jsonl"


def _checkpoint_dir(root, run_id="run_001"):
    return root / "runs" / run_id / "checkpoints"


def _history_candidate_files(root, run_id="run_001"):
    checkpoint_dir = _checkpoint_dir(root, run_id)
    if not checkpoint_dir.exists():
        return []
    return sorted(path for path in checkpoint_dir.glob("*.json") if path.name != "latest.json")


def test_file_checkpoint_store_exposes_explicit_history_save_method(tmp_path):
    store = checkpoint_store.FileCheckpointStore(tmp_path)

    assert hasattr(store, "save_checkpoint_history")


def test_save_checkpoint_remains_latest_only_replacement(tmp_path):
    store = checkpoint_store.FileCheckpointStore(tmp_path)
    first = _checkpoint(basis_event_id="evt_001", state={"version": "first"})
    second = _checkpoint(
        basis_event_id="evt_002",
        created_at="2026-04-28T00:00:02Z",
        state={"version": "second"},
    )

    store.save_checkpoint("run_001", first)
    store.save_checkpoint("run_001", second)

    checkpoint_dir = _checkpoint_dir(tmp_path)
    assert store.load_latest_checkpoint("run_001") == second
    assert sorted(path.name for path in checkpoint_dir.iterdir()) == ["latest.json"]
    assert json.loads((checkpoint_dir / "latest.json").read_text(encoding="utf-8")) == second


def test_save_checkpoint_history_does_not_overwrite_latest_checkpoint(tmp_path):
    store = checkpoint_store.FileCheckpointStore(tmp_path)
    latest = _checkpoint(basis_event_id="evt_001", state={"version": "latest"})
    historical = _checkpoint(
        basis_event_id="evt_002",
        created_at="2026-04-28T00:00:02Z",
        state={"version": "historical"},
    )
    store.save_checkpoint("run_001", latest)

    store.save_checkpoint_history("run_001", historical)

    assert store.load_latest_checkpoint("run_001") == latest
    assert _history_candidate_files(tmp_path)


@pytest.mark.parametrize(
    "invalid_checkpoint",
    [
        pytest.param(["not", "a", "dict"], id="non-dict-checkpoint"),
        pytest.param(
            {
                "run_id": "run_001",
                "projector_version": "run_projector@v1",
                "state": {"status": "opaque"},
                "created_at": "2026-04-28T00:00:01Z",
            },
            id="missing-required-field",
        ),
        pytest.param(_checkpoint(run_id="run_002"), id="run-id-mismatch"),
    ],
)
def test_save_checkpoint_history_rejects_invalid_checkpoint_without_writing_candidate(
    tmp_path,
    invalid_checkpoint,
):
    store = checkpoint_store.FileCheckpointStore(tmp_path)

    with pytest.raises((TypeError, ValueError)):
        store.save_checkpoint_history("run_001", invalid_checkpoint)

    assert _history_candidate_files(tmp_path) == []


def test_save_checkpoint_history_does_not_modify_event_log(tmp_path):
    store = checkpoint_store.FileCheckpointStore(tmp_path)
    event_log = _event_log_path(tmp_path)
    event_log.parent.mkdir(parents=True)
    event_log.write_text('{"event_id":"evt_001"}\n', encoding="utf-8")
    before = event_log.read_text(encoding="utf-8")

    store.save_checkpoint_history("run_001", _checkpoint())

    assert event_log.read_text(encoding="utf-8") == before


def test_save_checkpoint_history_candidates_are_loaded_newest_to_oldest(tmp_path):
    store = checkpoint_store.FileCheckpointStore(tmp_path)
    older = _checkpoint(
        basis_event_id="evt_001",
        created_at="2026-04-28T00:00:01Z",
        state={"version": "older"},
    )
    newer = _checkpoint(
        basis_event_id="evt_002",
        created_at="2026-04-28T00:00:02Z",
        state={"version": "newer"},
    )

    store.save_checkpoint_history("run_001", older)
    store.save_checkpoint_history("run_001", newer)

    candidates = store.load_checkpoint_candidates("run_001")
    assert [candidate["basis_event_id"] for candidate in candidates] == ["evt_002", "evt_001"]


def test_save_checkpoint_history_remains_storage_opaque(tmp_path):
    store = checkpoint_store.FileCheckpointStore(tmp_path)
    opaque_checkpoint = _checkpoint(
        basis_event_id="evt_999",
        state={"status": "opaque_to_storage"},
    )
    opaque_checkpoint["projector_version"] = "run_projector@future"
    opaque_checkpoint["integrity"] = {
        "algorithm": "unknown",
        "checkpoint_hash": "not-storage-business",
    }

    store.save_checkpoint_history("run_001", opaque_checkpoint)

    assert store.load_checkpoint_candidates("run_001") == [opaque_checkpoint]
