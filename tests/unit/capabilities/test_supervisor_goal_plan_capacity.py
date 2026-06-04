import json
from pathlib import Path

from isotope.capabilities.runner import CapabilityRunner
from isotope.features.supervisor.planner.goal_queue import read_active_supervisor_goals


class FakeGoalProvider:
    def __init__(self, *, expected_write: bool = False) -> None:
        self.expected_write = expected_write

    def summarize(self, messages: list[dict[str, str]]) -> str:
        user_payload = json.loads(messages[1]["content"])
        assert user_payload["user_goal"] == "把 dashboard 目标规划接入 capacity"
        assert user_payload["write_mode"] is self.expected_write
        return json.dumps(
            {
                "plan_summary": "把 dashboard 目标规划包装成可调用能力。",
                "goals": [
                    {
                        "goal": "新增 supervisor.goal_plan capacity。",
                        "target_name": "supervisor-goal-plan-capacity",
                        "reason": "dashboard 已有目标规划入口，capacity loop 还看不见。",
                    }
                ],
            },
            ensure_ascii=False,
        )


def _write_current_docs(root: Path) -> None:
    docs = root / "docs" / "current"
    docs.mkdir(parents=True)
    (docs / "status.md").write_text("Supervisor dashboard 已有目标规划。\n", encoding="utf-8")
    (docs / "agent-task-queue.md").write_text("capacity path 需要复用现有能力。\n", encoding="utf-8")
    (docs / "supervisor-capability-map.md").write_text("goal plan 尚未进入 capacity。\n", encoding="utf-8")


def test_supervisor_goal_plan_capability_previews_existing_goal_planner(
    tmp_path,
    monkeypatch,
):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _write_current_docs(workspace)
    codex_home = tmp_path / "codex-home"
    monkeypatch.setattr(
        "isotope.capabilities.supervisor_goal_plan.resolve_summary_provider_from_env",
        lambda **_: FakeGoalProvider(),
    )

    result = CapabilityRunner().run_capability(
        "supervisor.goal_plan",
        inputs={
            "state_root": str(codex_home),
            "cwd": str(workspace),
            "goal": "把 dashboard 目标规划接入 capacity",
        },
    )

    assert result["kind"] == "capability_run_result"
    assert result["capability_id"] == "supervisor.goal_plan"
    assert result["status"] == "completed"
    assert result["runner_kind"] == "supervisor_goal_plan"
    goal_plan = result["goal_plan"]
    assert goal_plan["mode"] == "preview"
    assert goal_plan["planning_trigger"] == "capacity"
    assert goal_plan["plan_summary"] == "把 dashboard 目标规划包装成可调用能力。"
    assert goal_plan["candidates"] == [
        {
            "goal": "新增 supervisor.goal_plan capacity。",
            "target_name": "supervisor-goal-plan-capacity",
            "reason": "dashboard 已有目标规划入口，capacity loop 还看不见。",
        }
    ]
    assert goal_plan["written_goals"] == []
    assert read_active_supervisor_goals(codex_home=codex_home) == ()


def test_supervisor_goal_plan_capability_writes_when_explicitly_requested(
    tmp_path,
    monkeypatch,
):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _write_current_docs(workspace)
    codex_home = tmp_path / "codex-home"
    monkeypatch.setattr(
        "isotope.capabilities.supervisor_goal_plan.resolve_summary_provider_from_env",
        lambda **_: FakeGoalProvider(expected_write=True),
    )

    result = CapabilityRunner().run_capability(
        "supervisor.goal_plan",
        inputs={
            "state_root": str(codex_home),
            "cwd": str(workspace),
            "goal": "把 dashboard 目标规划接入 capacity",
            "write": True,
        },
    )

    goal_plan = result["goal_plan"]
    assert goal_plan["mode"] == "write"
    assert [item["target_name"] for item in goal_plan["written_goals"]] == [
        "supervisor-goal-plan-capacity"
    ]
    active_goals = read_active_supervisor_goals(codex_home=codex_home)
    assert [item.target_name for item in active_goals] == [
        "supervisor-goal-plan-capacity"
    ]
