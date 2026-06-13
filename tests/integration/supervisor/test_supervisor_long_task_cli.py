from __future__ import annotations

import json

from isotope.llm.provider import LLMResponse
from isotope.runtime.in_process import InProcessServer

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


class CliDeterministicPlanner:
    provider = "cli_deterministic_long_task"
    model = "stub-cli-long-task"

    def __init__(self, root):
        self.root = root
        self.calls = 0

    def generate(self, messages, *, max_tokens=512):
        self.calls += 1
        task_line = (self.root / "long_tasks" / "tasks.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()[-1]
        run_id = json.loads(task_line)["run_id"]
        control = InProcessServer(self.root).get_agent_loop_control(run_id)
        return LLMResponse(
            provider=self.provider,
            model=self.model,
            content=json.dumps(
                {
                    "planner_run_id": f"planner_cli_{self.calls}",
                    "basis": {
                        "run_id": run_id,
                        "last_event_id": control["last_event_id"],
                    },
                    "decision": {
                        "step": "record_turn_memory",
                        "request": {
                            "summary": "cli tick",
                            "content": {"kind": "long_task_cli_tick"},
                            "scope": "run",
                            "source_refs": [],
                            "quality": "candidate",
                        },
                    },
                }
            ),
            finish_reason="stop",
            usage={},
            raw={"raw_response": "SHOULD_NOT_LEAK"},
        )


def test_supervisor_long_task_run_cli_uses_bounded_ticks(tmp_path, capsys, monkeypatch):
    planner = CliDeterministicPlanner(tmp_path)
    monkeypatch.setattr(
        "isotope.features.supervisor.commands.handlers.long_task.resolve_long_task_planner_provider_from_env",
        lambda: planner,
    )
    runner.main(
        [
            "long-task",
            "start",
            "--state-root",
            str(tmp_path),
            "--goal",
            "Run through CLI.",
            "--json",
        ]
    )
    task_id = json.loads(capsys.readouterr().out)["task"]["task_id"]

    assert (
        runner.main(
            [
                "long-task",
                "run",
                "--state-root",
                str(tmp_path),
                "--task-id",
                task_id,
                "--max-ticks",
                "1",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["task"]["summary"]["tick_count"] == 1
    assert payload["ticks"][0]["planner_summary"]["selected_step"] == "record_turn_memory"
    assert "raw_response" not in json.dumps(payload)
