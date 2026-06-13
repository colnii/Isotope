from __future__ import annotations

import json

import isotope.features.supervisor.runner as runner


def test_supervisor_long_task_start_status_and_list_cli(tmp_path, capsys):
    assert (
        runner.main(
            [
                "long-task",
                "start",
                "--state-root",
                str(tmp_path),
                "--goal",
                "Run from CLI.",
                "--json",
            ]
        )
        == 0
    )
    created = json.loads(capsys.readouterr().out)
    task_id = created["task"]["task_id"]

    assert (
        runner.main(
            [
                "long-task",
                "status",
                "--state-root",
                str(tmp_path),
                "--task-id",
                task_id,
                "--json",
            ]
        )
        == 0
    )
    status = json.loads(capsys.readouterr().out)
    assert status["task"]["goal"] == "Run from CLI."
    assert status["task"]["run_status"] == "running"

    assert (
        runner.main(
            [
                "long-task",
                "list",
                "--state-root",
                str(tmp_path),
                "--json",
            ]
        )
        == 0
    )
    listed = json.loads(capsys.readouterr().out)
    assert listed["summary"]["task_count"] == 1
    assert listed["tasks"][0]["task_id"] == task_id


def test_supervisor_long_task_pause_resume_stop_cli(tmp_path, capsys):
    runner.main(
        [
            "long-task",
            "start",
            "--state-root",
            str(tmp_path),
            "--goal",
            "Control from CLI.",
            "--json",
        ]
    )
    task_id = json.loads(capsys.readouterr().out)["task"]["task_id"]

    for command, expected_status in (
        ("pause", "paused"),
        ("resume", "queued"),
        ("stop", "stopped"),
    ):
        assert (
            runner.main(
                [
                    "long-task",
                    command,
                    "--state-root",
                    str(tmp_path),
                    "--task-id",
                    task_id,
                    "--reason",
                    f"{command} requested.",
                    "--json",
                ]
            )
            == 0
        )
        payload = json.loads(capsys.readouterr().out)
        assert payload["task"]["status"] == expected_status
