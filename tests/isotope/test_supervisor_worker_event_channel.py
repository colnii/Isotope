from __future__ import annotations

import json

from isotope.features.supervisor import runner


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
