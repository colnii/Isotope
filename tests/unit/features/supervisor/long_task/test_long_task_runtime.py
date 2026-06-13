from __future__ import annotations

import json
from typing import Any

from isotope.llm.provider import LLMResponse
from isotope.runtime.in_process import InProcessServer

from isotope.features.supervisor.long_task.runtime import (
    create_long_task,
    list_long_tasks,
    pause_long_task,
    run_long_task_ticks,
    resume_long_task,
    status_long_task,
    stop_long_task,
)


def test_create_long_task_creates_run_and_queued_projection(tmp_path):
    result = create_long_task(tmp_path, goal="Run a long Supervisor task.")

    assert result["status"] == "ok"
    assert result["task"]["status"] == "queued"
    assert result["task"]["goal"] == "Run a long Supervisor task."
    assert result["task"]["run_id"].startswith("run_")
    assert result["task"]["session_id"].startswith("session_")

    status = status_long_task(tmp_path, result["task"]["task_id"])
    assert status["task"]["task_id"] == result["task"]["task_id"]
    assert status["task"]["run_status"] == "running"


def test_pause_resume_and_stop_long_task_update_projection(tmp_path):
    task_id = create_long_task(tmp_path, goal="Pause me.")["task"]["task_id"]

    paused = pause_long_task(tmp_path, task_id, reason="Need user review.")
    assert paused["task"]["status"] == "paused"
    assert paused["task"]["requires_human"] is True

    resumed = resume_long_task(tmp_path, task_id, reason="Continue.")
    assert resumed["task"]["status"] == "queued"
    assert resumed["task"]["control_state"] == "resume"

    stopped = stop_long_task(tmp_path, task_id, reason="User stopped.")
    assert stopped["task"]["status"] == "stopped"
    assert stopped["task"]["requires_human"] is False


def test_list_long_tasks_returns_compact_summary(tmp_path):
    first = create_long_task(tmp_path, goal="First.")["task"]["task_id"]
    second = create_long_task(tmp_path, goal="Second.")["task"]["task_id"]
    pause_long_task(tmp_path, first, reason="Hold first.")

    result = list_long_tasks(tmp_path)

    assert result["status"] == "ok"
    assert result["summary"]["task_count"] == 2
    assert result["summary"]["requires_human_count"] == 1
    assert {task["task_id"] for task in result["tasks"]} == {first, second}


class DeterministicLongTaskPlanner:
    provider = "deterministic_long_task"
    model = "stub-long-task-planner"

    def __init__(self, root):
        self.root = root
        self.calls: list[dict[str, Any]] = []

    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 512,
    ) -> LLMResponse:
        self.calls.append({"messages": messages, "max_tokens": max_tokens})
        run_id = self._run_id()
        control = InProcessServer(self.root).get_agent_loop_control(run_id)
        payload = {
            "planner_run_id": f"planner_{len(self.calls)}",
            "basis": {
                "run_id": run_id,
                "last_event_id": control["last_event_id"],
            },
            "decision": {
                "step": "record_turn_memory",
                "request": {
                    "summary": f"tick {len(self.calls)} summary",
                    "content": {
                        "kind": "long_task_tick",
                        "tick": len(self.calls),
                    },
                    "scope": "run",
                    "source_refs": [],
                    "quality": "candidate",
                },
            },
        }
        return LLMResponse(
            provider=self.provider,
            model=self.model,
            content=json.dumps(payload),
            finish_reason="stop",
            usage={"prompt_tokens": 1, "completion_tokens": 1},
            raw={"raw_response": "SHOULD_NOT_LEAK"},
        )

    def _run_id(self) -> str:
        tasks = (self.root / "long_tasks" / "tasks.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
        return json.loads(tasks[-1])["run_id"]


def test_run_long_task_ticks_advances_bounded_ticks_without_raw_payload(tmp_path):
    task_id = create_long_task(tmp_path, goal="Run bounded ticks.")["task"]["task_id"]
    provider = DeterministicLongTaskPlanner(tmp_path)

    result = run_long_task_ticks(tmp_path, task_id, provider=provider, max_ticks=2)

    assert result["status"] == "ok"
    assert result["task"]["summary"]["tick_count"] == 2
    assert result["task"]["status"] in {"queued", "blocked", "completed"}
    assert len(result["ticks"]) == 2
    assert result["ticks"][0]["planner_summary"]["selected_step"] == "record_turn_memory"
    assert "raw_response" not in json.dumps(result)


def test_run_long_task_ticks_honors_pause_before_next_tick(tmp_path):
    task_id = create_long_task(tmp_path, goal="Pause before run.")["task"]["task_id"]
    pause_long_task(tmp_path, task_id, reason="Hold.")

    result = run_long_task_ticks(
        tmp_path,
        task_id,
        provider=DeterministicLongTaskPlanner(tmp_path),
        max_ticks=1,
    )

    assert result["task"]["status"] == "paused"
    assert result["ticks"] == []
    assert result["stop_reason"] == "user_paused"
