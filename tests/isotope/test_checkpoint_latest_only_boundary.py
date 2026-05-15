import json

import pytest

import isotope.platform.state.checkpoint_store as checkpoint_store


INVALID_RUN_IDS = ["", ".", "..", "run/001", "run\\001", "../run_001"]


def _checkpoint(run_id="run_001", basis_event_id="evt_001", state=None):
    return {
        "run_id": run_id,
        "projector_version": "run_projector@v1",
        "basis_event_id": basis_event_id,
        "state": state or {"status": "opaque"},
        "created_at": "2026-04-28T00:00:00Z",
    }


def test_save_checkpoint_replaces_latest_without_history_files(tmp_path):
    store = checkpoint_store.FileCheckpointStore(tmp_path)
    first = _checkpoint(basis_event_id="evt_001", state={"version": "first"})
    second = _checkpoint(basis_event_id="evt_002", state={"version": "second"})

    store.save_checkpoint("run_001", first)
    store.save_checkpoint("run_001", second)

    checkpoint_dir = tmp_path / "runs" / "run_001" / "checkpoints"
    assert store.load_latest_checkpoint("run_001") == second
    assert sorted(path.name for path in checkpoint_dir.iterdir()) == ["latest.json"]
    assert json.loads((checkpoint_dir / "latest.json").read_text(encoding="utf-8")) == second


def test_replacement_does_not_modify_event_log(tmp_path):
    store = checkpoint_store.FileCheckpointStore(tmp_path)
    event_log = tmp_path / "runs" / "run_001" / "events.jsonl"
    event_log.parent.mkdir(parents=True)
    event_log.write_text('{"event_id":"evt_001"}\n', encoding="utf-8")
    before = event_log.read_text(encoding="utf-8")

    store.save_checkpoint("run_001", _checkpoint(basis_event_id="evt_001"))
    store.save_checkpoint("run_001", _checkpoint(basis_event_id="evt_002"))

    assert event_log.read_text(encoding="utf-8") == before


@pytest.mark.parametrize(
    "invalid_checkpoint",
    [
        pytest.param(
            {
                "run_id": "run_001",
                "projector_version": "run_projector@v1",
                "state": {"status": "opaque"},
                "created_at": "2026-04-28T00:00:00Z",
            },
            id="missing-required-field",
        ),
        pytest.param(_checkpoint(run_id="run_002"), id="run-id-mismatch"),
    ],
)
def test_invalid_replacement_does_not_overwrite_existing_latest(tmp_path, invalid_checkpoint):
    store = checkpoint_store.FileCheckpointStore(tmp_path)
    valid = _checkpoint()
    store.save_checkpoint("run_001", valid)

    with pytest.raises(ValueError):
        store.save_checkpoint("run_001", invalid_checkpoint)

    assert store.load_latest_checkpoint("run_001") == valid


@pytest.mark.parametrize("bad_run_id", INVALID_RUN_IDS)
def test_save_checkpoint_rejects_invalid_run_id_path_segments(tmp_path, bad_run_id):
    store = checkpoint_store.FileCheckpointStore(tmp_path)

    with pytest.raises(ValueError, match="run_id"):
        store.save_checkpoint(bad_run_id, _checkpoint(run_id=bad_run_id))

    runs_dir = tmp_path / "runs"
    if runs_dir.exists():
        assert list(runs_dir.rglob("latest.json")) == []


@pytest.mark.parametrize("bad_run_id", INVALID_RUN_IDS)
def test_load_latest_checkpoint_rejects_invalid_run_id_path_segments(tmp_path, bad_run_id):
    store = checkpoint_store.FileCheckpointStore(tmp_path)

    with pytest.raises(ValueError, match="run_id"):
        store.load_latest_checkpoint(bad_run_id)


@pytest.mark.parametrize("bad_run_id", INVALID_RUN_IDS)
def test_checkpoint_path_rejects_invalid_run_id_path_segments(tmp_path, bad_run_id):
    store = checkpoint_store.FileCheckpointStore(tmp_path)

    with pytest.raises(ValueError, match="run_id"):
        store.checkpoint_path(bad_run_id)
