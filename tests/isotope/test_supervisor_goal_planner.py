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


class SeededGoalProvider:
    def __init__(self, expected_goal: str, workspace: Path) -> None:
        self.expected_goal = expected_goal
        self.workspace = workspace
        self.seen_user_goal = False

    def summarize(self, messages: list[dict[str, str]]) -> str:
        user_payload = json.loads(messages[1]["content"])
        assert user_payload["user_goal"] == self.expected_goal
        self.seen_user_goal = True
        return json.dumps(
            {
                "goals": [
                    {
                        "goal": "把高层目标拆成可由 daemon 消费的目标队列项。",
                        "target_name": "supervisor-autopilot-goal-entry",
                        "reason": "用户给出一句高层目标，需要进入持久目标队列。",
                    }
                ]
            },
            ensure_ascii=False,
        )


class BoardPlanGoalProvider:
    def summarize(self, messages: list[dict[str, str]]) -> str:
        user_payload = json.loads(messages[1]["content"])
        schema = user_payload["output_schema"]
        assert "plan_summary" in schema
        assert "phases" in schema
        assert "parallel_recommendations" in schema
        assert "stop_conditions" in schema
        assert "acceptance_conditions" in schema
        return json.dumps(
            {
                "plan_summary": "把 Supervisor dashboard 作为完整板块推进。",
                "phases": [
                    {
                        "name": "入口收敛",
                        "goals": ["梳理 dashboard 刷新和托管输出入口。"],
                        "stop_conditions": ["发现入口 contract 冲突时暂停。"],
                        "acceptance_conditions": ["入口 contract 有 pytest 覆盖。"],
                    },
                    {
                        "name": "并行实现",
                        "goals": ["拆分状态按钮和 hosted output 展示。"],
                    },
                ],
                "parallel_recommendations": [
                    {
                        "batch": "批次 2",
                        "targets": [
                            "supervisor-status-buttons",
                            "supervisor-hosted-output",
                        ],
                        "reason": "两个目标写入区域不同，可并行。",
                    }
                ],
                "stop_conditions": ["任一 worker 返回 needs_user 时停止继续派发。"],
                "acceptance_conditions": ["dashboard 可看到刷新后的 goals 和 worker 状态。"],
                "goals": [
                    {
                        "goal": "补 Supervisor dashboard 刷新验收。",
                        "target_name": "supervisor-dashboard-refresh",
                        "reason": "板块计划第一阶段需要先锁入口。",
                    }
                ],
            },
            ensure_ascii=False,
        )


class ParallelWriteGoalProvider:
    def summarize(self, messages: list[dict[str, str]]) -> str:
        return json.dumps(
            {
                "parallel_recommendations": [
                    {
                        "batch": "并行批次",
                        "targets": ["worker-a", "worker-b"],
                        "reason": "两个目标可独立落地。",
                    }
                ],
                "goals": [
                    {
                        "goal": "实现 worker A。",
                        "target_name": "worker-a",
                        "reason": "A 可独立执行。",
                    },
                    {
                        "goal": "实现 worker B。",
                        "target_name": "worker-b",
                        "reason": "B 可独立执行。",
                    },
                ],
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


def test_supervisor_goal_plan_can_fanout_execute_parallel_recommendations(
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
        lambda **_: ParallelWriteGoalProvider(),
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner._prepare_launch_worktree",
        lambda *, cwd, target_name: {
            "enabled": False,
            "source_cwd": str(cwd),
            "cwd": str(cwd),
            "reason": "test_stub",
        },
    )
    captured: list[list[str]] = []

    class FakeProcess:
        def __init__(self, pid: int) -> None:
            self.pid = pid

    def fake_popen(
        command: list[str],
        *,
        cwd: str,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> FakeProcess:
        captured.append(command)
        return FakeProcess(45700 + len(captured))

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.Popen", fake_popen)

    exit_code = supervisor_main(
        [
            "goal",
            "plan",
            "--codex-home",
            str(codex_home),
            "--cwd",
            str(root),
            "--write",
            "--fanout-execute",
            "--max-fanout-launches",
            "1",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert [goal["target_name"] for goal in payload["written_goals"]] == [
        "worker-a",
        "worker-b",
    ]
    assert payload["fanout_plan"]["summary"] == {
        "launchable": 1,
        "skipped": 1,
        "limit": 1,
    }
    assert payload["fanout_plan"]["skipped"] == [
        {
            "target_name": "worker-b",
            "reason": "fanout_limit_reached",
            "batch": "并行批次",
        }
    ]
    assert payload["fanout_plan"]["launch_specs"][0]["review"][
        "requires_human_review"
    ] is False
    assert payload["executed"]["summary"] == {
        "launched": 1,
        "skipped": 0,
        "limit": 1,
    }
    assert payload["executed"]["results"][0]["managed"]["name"] == "worker-a"
    assert len(captured) == 1


def test_supervisor_goal_plan_surfaces_board_level_review_plan(
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
        lambda **_: BoardPlanGoalProvider(),
    )

    exit_code = supervisor_main(
        [
            "goal",
            "plan",
            "推进 Supervisor dashboard 完整板块",
            "--codex-home",
            str(codex_home),
            "--cwd",
            str(root),
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["plan_summary"] == "把 Supervisor dashboard 作为完整板块推进。"
    assert payload["phases"] == [
        {
            "name": "入口收敛",
            "goals": ["梳理 dashboard 刷新和托管输出入口。"],
            "stop_conditions": ["发现入口 contract 冲突时暂停。"],
            "acceptance_conditions": ["入口 contract 有 pytest 覆盖。"],
        },
        {
            "name": "并行实现",
            "goals": ["拆分状态按钮和 hosted output 展示。"],
        },
    ]
    assert payload["parallel_recommendations"] == [
        {
            "batch": "批次 2",
            "targets": [
                "supervisor-status-buttons",
                "supervisor-hosted-output",
            ],
            "reason": "两个目标写入区域不同，可并行。",
        }
    ]
    assert payload["stop_conditions"] == ["任一 worker 返回 needs_user 时停止继续派发。"]
    assert payload["acceptance_conditions"] == [
        "dashboard 可看到刷新后的 goals 和 worker 状态。"
    ]
    assert payload["candidates"][0]["target_name"] == "supervisor-dashboard-refresh"
    assert payload["written_goals"] == []
    assert read_active_supervisor_goals(codex_home=codex_home) == ()


def test_supervisor_goal_add_accepts_positional_one_sentence_goal(tmp_path, capsys):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    goal = "一句话进入 Supervisor 目标队列。"

    exit_code = supervisor_main(
        [
            "goal",
            "add",
            goal,
            "--codex-home",
            str(tmp_path / ".codex"),
            "--cwd",
            str(workspace),
            "--target-name",
            "one-sentence-goal",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["goal"]["goal"] == goal
    assert payload["goal"]["target_name"] == "one-sentence-goal"
    assert payload["active_goals"][0]["goal"] == goal


def test_supervisor_goal_plan_write_feeds_loop_without_explicit_goal(
    tmp_path,
    capsys,
    monkeypatch,
):
    root = tmp_path / "repo"
    root.mkdir()
    _write_current_docs(root)
    codex_home = tmp_path / ".codex"
    user_goal = "减少人类主控 Codex 参与。"
    provider = SeededGoalProvider(user_goal, root)
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: provider,
    )

    exit_code = supervisor_main(
        [
            "goal",
            "plan",
            user_goal,
            "--codex-home",
            str(codex_home),
            "--cwd",
            str(root),
            "--write",
            "--json",
        ]
    )

    assert exit_code == 0
    plan_payload = json.loads(capsys.readouterr().out)
    assert provider.seen_user_goal is True
    assert plan_payload["user_goal"] == user_goal
    assert plan_payload["written_goals"][0]["target_name"] == (
        "supervisor-autopilot-goal-entry"
    )

    class LoopProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            content = messages[1]["content"]
            assert "把高层目标拆成可由 daemon 消费的目标队列项。" in content
            assert '"target_name": "supervisor-autopilot-goal-entry"' in content
            return json.dumps(
                {
                    "kind": "launch_session",
                    "target_name": "supervisor-autopilot-goal-entry",
                    "cwd": str(root),
                    "prompt": "把高层目标拆成可由 daemon 消费的目标队列项。",
                    "reason": "loop 没有显式 goal 时消费 active_goals。",
                },
                ensure_ascii=False,
            )

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: LoopProvider(),
    )
    captured: dict[str, object] = {}

    class FakeProcess:
        pid = 45682

    def fake_popen(
        command: list[str],
        *,
        cwd: str,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> FakeProcess:
        captured["command"] = command
        captured["cwd"] = cwd
        return FakeProcess()

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.Popen", fake_popen)

    exit_code = supervisor_main(
        [
            "loop",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "1",
            "--interval",
            "1",
            "--no-auto-adopt",
            "--json",
        ]
    )

    assert exit_code == 0
    loop_payload = json.loads(capsys.readouterr().out)
    assert loop_payload["active_goals"] == plan_payload["written_goals"]
    assert loop_payload["llm_action"]["target_name"] == "supervisor-autopilot-goal-entry"
    assert loop_payload["executed"]["managed"]["name"] == "supervisor-autopilot-goal-entry"
    assert captured["command"][9].startswith("WORK ORDER")
    assert "goal: 把高层目标拆成可由 daemon 消费的目标队列项。" in captured["command"][9]


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
