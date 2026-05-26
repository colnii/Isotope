from __future__ import annotations

import json

import isotope.memory.worker_event_channel as memory_worker_event_channel
import isotope.platform.state.worker_event_channel as platform_worker_event_channel
from isotope.features.supervisor import runner
from isotope.platform.schemas.memory import MemoryRecord
from isotope.platform.state.worker_event_channel import WorkerEvent


def test_worker_event_channel_uses_platform_state_implementation():
    assert (
        memory_worker_event_channel.publish_worker_event
        is platform_worker_event_channel.publish_worker_event
    )
    assert (
        memory_worker_event_channel.list_worker_events
        is platform_worker_event_channel.list_worker_events
    )
    assert (
        memory_worker_event_channel.render_worker_event_channel_plain
        is platform_worker_event_channel.render_worker_event_channel_plain
    )


def test_worker_event_schema_builds_memory_record_without_raw_content():
    event = WorkerEvent(
        event_id="mem_event_test",
        channel="reviews",
        event_type="handoff",
        from_worker="worker-a",
        to_worker="worker-b",
        message="Ready for review.",
        payload={"branch": "feature/a"},
        created_at="2026-05-24T01:02:03Z",
        execution_id="exec_event_test",
    )

    record = event.to_memory_record()

    assert isinstance(record, MemoryRecord)
    assert record.memory_id == "mem_event_test"
    assert record.scope == "session"
    assert record.content == {
        "kind": "worker_event",
        "channel": "reviews",
        "event_type": "handoff",
        "from_worker": "worker-a",
        "to_worker": "worker-b",
        "message": "Ready for review.",
        "payload": {"branch": "feature/a"},
    }
    assert record.summary == "worker-a -> worker-b / handoff / Ready for review."
    assert record.provenance == {
        "run_id": "supervisor_worker_event_channel",
        "execution_id": "exec_event_test",
        "action_type": "worker_event",
    }
    assert record.quality == "worker_event"
    assert "raw_content" not in record.content


def test_worker_event_schema_rejects_empty_required_text():
    try:
        WorkerEvent(
            event_id="mem_event_test",
            channel="reviews",
            event_type="handoff",
            from_worker=" ",
            to_worker="worker-b",
            message="Ready for review.",
            payload={},
            created_at="2026-05-24T01:02:03Z",
            execution_id="exec_event_test",
        )
    except ValueError as exc:
        assert "from_worker must be a non-empty string" in str(exc)
    else:
        raise AssertionError("WorkerEvent must reject empty from_worker")


def test_supervisor_worker_event_channel_publish_and_list_json(tmp_path, capsys):
    assert (
        runner.main(
            [
                "worker-event",
                "publish",
                "--root",
                str(tmp_path),
                "--from",
                "worker-a",
                "--to",
                "worker-b",
                "--type",
                "handoff",
                "--message",
                "Ready for review.",
                "--payload-json",
                '{"branch": "feature/a"}',
                "--json",
            ]
        )
        == 0
    )
    publish_output = capsys.readouterr().out
    published = json.loads(publish_output)
    assert published["status"] == "ok"
    assert published["event"]["from_worker"] == "worker-a"
    assert published["event"]["to_worker"] == "worker-b"
    assert published["event"]["payload"] == {"branch": "feature/a"}
    assert "content" not in published["event"]

    assert (
        runner.main(
            [
                "worker-event",
                "list",
                "--root",
                str(tmp_path),
                "--to",
                "worker-b",
                "--json",
            ]
        )
        == 0
    )
    list_output = capsys.readouterr().out
    payload = json.loads(list_output)
    assert payload["status"] == "ok"
    assert payload["summary"]["total"] == 1
    assert payload["events"][0]["event_type"] == "handoff"
    assert payload["events"][0]["message"] == "Ready for review."
    assert payload["events"][0]["payload"] == {"branch": "feature/a"}
    assert "content" not in payload["events"][0]
    assert "content" not in list_output


def test_supervisor_worker_event_channel_plain_list_filters_receiver(tmp_path, capsys):
    _publish(tmp_path, from_worker="worker-a", to_worker="worker-b", message="For B")
    _publish(tmp_path, from_worker="worker-a", to_worker="worker-c", message="For C")
    _publish(tmp_path, from_worker="worker-a", to_worker=None, message="Broadcast")
    capsys.readouterr()

    assert (
        runner.main(
            [
                "worker-event",
                "list",
                "--root",
                str(tmp_path),
                "--to",
                "worker-b",
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "Worker event channel" in output
    assert "total: 2" in output
    assert "worker-a -> worker-b / message / For B" in output
    assert "worker-a -> * / message / Broadcast" in output
    assert "For C" not in output


def _publish(tmp_path, *, from_worker: str, to_worker: str | None, message: str) -> None:
    args = [
        "worker-event",
        "publish",
        "--root",
        str(tmp_path),
        "--from",
        from_worker,
        "--message",
        message,
    ]
    if to_worker is not None:
        args.extend(["--to", to_worker])
    assert runner.main(args) == 0
