import json
from pathlib import Path

from isotope.features.supervisor.goal_planner import parse_goal_candidates
from isotope.features.supervisor.goal_queue import read_active_supervisor_goals
from isotope.features.supervisor.runner import main as supervisor_main


class FakeGoalProvider:
    def __init__(self) -> None:
        self.messages: list[list[dict[str, str]]] = []

    def summarize(self, messages: list[dict[str, str]]) -> str:
        self.messages.append(messages)
        user_payload = json.loads(messages[1]["content"])
        assert "docs/current/status.md" in user_payload["facts"]
        assert "docs/current/agent-task-queue.md" in user_payload["facts"]
        assert "docs/current/supervisor-capability-map.md" in user_payload["facts"]
        assert isinstance(user_payload["write_mode"], bool)
        return json.dumps(
            {
                "goals": [
                    {
                        "goal": "为 Supervisor web 增加目标队列状态筛选。",
                        "target_name": "supervisor-web-goal-filter",
                        "reason": "状态文档显示目标队列已经进入日常 loop。",
                    },
                    {
                        "goal": "补一条 daemon status 展示 goal plan 来源的验收。",
                        "target_name": "supervisor-daemon-goal-plan-status",
                        "reason": "能力地图登记了 daemon status 聚合。",
                    },
                ]
            },
            ensure_ascii=False,
        )


class NonJsonGoalProvider:
    def summarize(self, messages: list[dict[str, str]]) -> str:
        return "我需要更多上下文，暂时不能给出目标。"


def _write_current_docs(root: Path) -> None:
    docs = root / "docs" / "current"
    docs.mkdir(parents=True)
    (docs / "status.md").write_text(
        "18. Supervisor loop 已消费持久目标队列。\n",
        encoding="utf-8",
    )
    (docs / "agent-task-queue.md").write_text(
        "- 下一步：增强 Supervisor 目标队列可见性。\n",
        encoding="utf-8",
    )
    (docs / "supervisor-capability-map.md").write_text(
        "- `goal add/list/archive` 已登记。\n",
        encoding="utf-8",
    )


def test_supervisor_goal_plan_previews_llm_generated_candidates(
    tmp_path,
    capsys,
    monkeypatch,
):
    root = tmp_path / "repo"
    root.mkdir()
    _write_current_docs(root)
    codex_home = tmp_path / ".codex"
    provider = FakeGoalProvider()
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: provider,
    )

    exit_code = supervisor_main(
        [
            "goal",
            "plan",
            "--codex-home",
            str(codex_home),
            "--cwd",
            str(root),
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["mode"] == "preview"
    assert [item["target_name"] for item in payload["candidates"]] == [
        "supervisor-web-goal-filter",
        "supervisor-daemon-goal-plan-status",
    ]
    assert payload["written_goals"] == []
    assert read_active_supervisor_goals(codex_home=codex_home) == ()


def test_supervisor_goal_plan_writes_selected_candidates(
    tmp_path,
    capsys,
    monkeypatch,
):
    root = tmp_path / "repo"
    root.mkdir()
    _write_current_docs(root)
    codex_home = tmp_path / ".codex"
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: FakeGoalProvider(),
    )

    exit_code = supervisor_main(
        [
            "goal",
            "plan",
            "--codex-home",
            str(codex_home),
            "--cwd",
            str(root),
            "--limit",
            "1",
            "--write",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "write"
    assert len(payload["candidates"]) == 1
    assert len(payload["written_goals"]) == 1
    active = read_active_supervisor_goals(codex_home=codex_home)
    assert len(active) == 1
    assert active[0].goal == "为 Supervisor web 增加目标队列状态筛选。"
    assert active[0].target_name == "supervisor-web-goal-filter"


def test_supervisor_goal_plan_extracts_json_fragment_after_explanatory_text():
    candidates = parse_goal_candidates(
        "先说明：不要使用这个示例 {\"goals\": []}。\n"
        "```json\n"
        "{\"goals\":[{\"goal\":\"修复 active goal 调度。\","
        "\"target_name\":\"active-goal-routing\","
        "\"reason\":\"当前目标队列仍有活跃项。\"}]}\n"
        "```"
    )

    assert [candidate.to_dict() for candidate in candidates] == [
        {
            "goal": "修复 active goal 调度。",
            "target_name": "active-goal-routing",
            "reason": "当前目标队列仍有活跃项。",
        }
    ]


def test_supervisor_goal_plan_extracts_noisy_json_array_fragment():
    candidates = parse_goal_candidates(
        "候选如下：\n"
        "[{\"goal\":\"补 goal plan JSON 降级测试。\","
        "\"target_name\":\"goal-plan-json-fallback\","
        "\"reason\":\"LLM 可能返回数组片段。\"}]"
    )

    assert candidates[0].target_name == "goal-plan-json-fallback"


def test_supervisor_goal_plan_ignores_later_non_goal_json_fragment():
    candidates = parse_goal_candidates(
        "真正的目标："
        "{\"goals\":[{\"goal\":\"修复 active goal 调度。\","
        "\"target_name\":\"active-goal-routing\","
        "\"reason\":\"当前目标队列仍有活跃项。\"}]}\n"
        "补充编号：[1, 2]"
    )

    assert [candidate.to_dict() for candidate in candidates] == [
        {
            "goal": "修复 active goal 调度。",
            "target_name": "active-goal-routing",
            "reason": "当前目标队列仍有活跃项。",
        }
    ]


def test_supervisor_goal_plan_json_reports_actionable_parse_error(
    tmp_path,
    capsys,
    monkeypatch,
):
    root = tmp_path / "repo"
    root.mkdir()
    _write_current_docs(root)
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: NonJsonGoalProvider(),
    )

    exit_code = supervisor_main(
        [
            "goal",
            "plan",
            "--codex-home",
            str(tmp_path / ".codex"),
            "--cwd",
            str(root),
            "--json",
        ]
    )

    assert exit_code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "error"
    message = payload["error"]["message"]
    assert "usable goals JSON" in message
    assert "invalid JSON" not in message


def test_supervisor_goal_plan_without_llm_provider_returns_visible_error(
    tmp_path,
    capsys,
    monkeypatch,
):
    root = tmp_path / "repo"
    root.mkdir()
    _write_current_docs(root)
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: (_ for _ in ()).throw(ValueError("No LLM pool entries found.")),
    )

    exit_code = supervisor_main(
        [
            "goal",
            "plan",
            "--codex-home",
            str(tmp_path / ".codex"),
            "--cwd",
            str(root),
            "--json",
        ]
    )

    assert exit_code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "error"
    assert "No LLM pool entries found" in payload["error"]["message"]
