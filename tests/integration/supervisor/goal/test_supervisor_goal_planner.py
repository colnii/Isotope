import json
from pathlib import Path

from isotope.features.supervisor.planner.goal_planner import (
    build_goal_planning_messages,
    parse_goal_candidates,
    parse_goal_planning_result,
)
from isotope.features.supervisor.planner.goal_queue import read_active_supervisor_goals
from isotope.features.supervisor.runner import main as supervisor_main


class StubGoalProvider:
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


class FourGoalProvider:
    def summarize(self, messages: list[dict[str, str]]) -> str:
        user_payload = json.loads(messages[1]["content"])
        assert user_payload["parallel_launch_limit"] == 3
        assert "goal_count_limit" not in user_payload
        return json.dumps(
            {
                "parallel_recommendations": [
                    {
                        "batch": "第一批",
                        "targets": ["worker-a", "worker-b", "worker-c"],
                        "reason": "前三个目标可先并行。",
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
                    {
                        "goal": "实现 worker C。",
                        "target_name": "worker-c",
                        "reason": "C 可独立执行。",
                    },
                    {
                        "goal": "实现 worker D。",
                        "target_name": "worker-d",
                        "reason": "D 是后续目标，不能被规划截断丢弃。",
                    },
                ],
            },
            ensure_ascii=False,
        )


class DependencyGraphGoalProvider:
    def summarize(self, messages: list[dict[str, str]]) -> str:
        user_payload = json.loads(messages[1]["content"])
        goal_schema = user_payload["output_schema"]["goals"][0]
        assert "depends_on" in goal_schema
        assert "stage" in goal_schema
        assert "scope" in goal_schema
        assert "merge_gate" in goal_schema
        return json.dumps(
            {
                "parallel_recommendations": [
                    {
                        "batch": "第二阶段",
                        "targets": ["worker-a", "worker-b"],
                        "reason": "planner 认为两者可进入 fanout gate。",
                    }
                ],
                "goals": [
                    {
                        "goal": "实现 worker A。",
                        "target_name": "worker-a",
                        "reason": "A 是基础阶段。",
                        "stage": "foundation",
                        "scope": "scheduler",
                    },
                    {
                        "goal": "实现 worker B。",
                        "target_name": "worker-b",
                        "reason": "B 依赖 A 合入后再启动。",
                        "depends_on": ["worker-a"],
                        "stage": "fanout",
                        "scope": "scheduler",
                        "merge_gate": "merge-foundation",
                    },
                ],
            },
            ensure_ascii=False,
        )


class SoftSyntaxRepairGoalProvider:
    def __init__(self) -> None:
        self.calls: list[list[dict[str, str]]] = []

    def summarize(self, messages: list[dict[str, str]]) -> str:
        self.calls.append(messages)
        if len(self.calls) == 1:
            return (
                "规划摘要：并行推进三个板块\n"
                "目标一：模块化 Supervisor。\n"
                "目标名：supervisor-modularization\n"
                "依据：runner.py 已经过大。\n"
            )
        user_payload = json.loads(messages[1]["content"])
        assert user_payload["task"] == "repair_goal_planning_output"
        assert "模块化 Supervisor" in user_payload["raw_answer"]
        return json.dumps(
            {
                "plan_summary": "并行推进三个板块",
                "goals": [
                    {
                        "goal": "模块化 Supervisor。",
                        "target_name": "supervisor-modularization",
                        "reason": "runner.py 已经过大。",
                    }
                ],
            },
            ensure_ascii=False,
        )


class TomlGoalProvider:
    def __init__(self) -> None:
        self.calls = 0

    def summarize(self, messages: list[dict[str, str]]) -> str:
        self.calls += 1
        return (
            'plan_summary = "并行推进三个板块"\n'
            'acceptance_conditions = ["目标可写入队列"]\n\n'
            '[[parallel_recommendations]]\n'
            'batch = "第一批"\n'
            'targets = ["supervisor-modularization", "memory-storage-layer"]\n'
            'reason = "两个目标边界不同"\n\n'
            '[[goals]]\n'
            'goal = "模块化 Supervisor。"\n'
            'target_name = "supervisor-modularization"\n'
            'reason = "runner.py 已经过大。"\n\n'
            '[[goals]]\n'
            'goal = "建立 memory 存储层。"\n'
            'target_name = "memory-storage-layer"\n'
            'reason = "memory 架构需要先落存储接口。"\n'
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
    provider = StubGoalProvider()
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
        lambda **_: StubGoalProvider(),
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
    assert len(payload["candidates"]) == 2
    assert len(payload["written_goals"]) == 2
    active = read_active_supervisor_goals(codex_home=codex_home)
    assert len(active) == 2
    assert active[0].goal == "为 Supervisor web 增加目标队列状态筛选。"
    assert active[0].target_name == "supervisor-web-goal-filter"


def test_supervisor_goal_plan_limit_does_not_truncate_planned_candidates(
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
        lambda **_: FourGoalProvider(),
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
            "3",
            "--write",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert [item["target_name"] for item in payload["candidates"]] == [
        "worker-a",
        "worker-b",
        "worker-c",
        "worker-d",
    ]
    assert [item["target_name"] for item in payload["written_goals"]] == [
        "worker-a",
        "worker-b",
        "worker-c",
        "worker-d",
    ]
    assert payload["parallel_launch_limit"] == 3
    assert read_active_supervisor_goals(codex_home=codex_home)[-1].target_name == (
        "worker-d"
    )


def test_supervisor_goal_plan_and_active_goals_preserve_dependency_graph_fields(
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
        lambda **_: DependencyGraphGoalProvider(),
    )

    exit_code = supervisor_main(
        [
            "goal",
            "plan",
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
    assert plan_payload["written_goals"][1]["depends_on"] == ["worker-a"]
    assert plan_payload["written_goals"][1]["stage"] == "fanout"
    assert plan_payload["written_goals"][1]["scope"] == "scheduler"
    assert plan_payload["written_goals"][1]["merge_gate"] == "merge-foundation"

    exit_code = supervisor_main(
        [
            "goal",
            "list",
            "--codex-home",
            str(codex_home),
            "--json",
        ]
    )

    assert exit_code == 0
    list_payload = json.loads(capsys.readouterr().out)
    assert list_payload["active_goals"][1]["depends_on"] == ["worker-a"]
    assert list_payload["active_goals"][1]["stage"] == "fanout"
    assert list_payload["active_goals"][1]["scope"] == "scheduler"
    assert list_payload["active_goals"][1]["merge_gate"] == "merge-foundation"


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
    prepared_target_names: list[str] = []
    captured_cwds: list[str] = []

    def stub_prepare_launch_worktree(*, cwd, target_name):
        prepared_target_names.append(target_name)
        worker_cwd = root / ".worktrees" / "supervisor" / target_name
        worker_cwd.mkdir(parents=True)
        return {
            "enabled": False,
            "source_cwd": str(cwd),
            "cwd": str(worker_cwd),
            "reason": "test_stub",
        }

    monkeypatch.setattr(
        "isotope.features.supervisor.runner._prepare_launch_worktree",
        stub_prepare_launch_worktree,
    )
    captured: list[list[str]] = []

    class StubProcess:
        def __init__(self, pid: int) -> None:
            self.pid = pid

    def stub_popen(
        command: list[str],
        *,
        cwd: str,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> StubProcess:
        captured.append(command)
        captured_cwds.append(cwd)
        return StubProcess(45700 + len(captured))

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.Popen", stub_popen)

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
            "2",
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
        "launchable": 2,
        "skipped": 0,
        "limit": 2,
    }
    assert payload["fanout_plan"]["skipped"] == []
    assert payload["fanout_plan"]["launch_specs"][0]["review"][
        "requires_human_review"
    ] is False
    assert payload["executed"]["summary"] == {
        "launched": 2,
        "skipped": 0,
        "limit": 2,
    }
    assert [item["managed"]["name"] for item in payload["executed"]["results"]] == [
        "worker-a",
        "worker-b",
    ]
    assert prepared_target_names == ["worker-a", "worker-b"]
    assert captured_cwds == [
        str(root / ".worktrees" / "supervisor" / "worker-a"),
        str(root / ".worktrees" / "supervisor" / "worker-b"),
    ]
    assert len(captured) == 2


def test_supervisor_goal_plan_fanout_records_launch_errors_and_continues(
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
    attempted: list[str] = []

    def stub_execute_launch_action(args, action):
        target_name = action["target_name"]
        attempted.append(target_name)
        if target_name == "worker-a":
            raise RuntimeError("boom worker-a")
        return {
            "kind": "launch_session",
            "managed": {
                "name": target_name,
                "record_id": f"managed-{target_name}",
                "pid": 45702,
                "backend": "process",
            },
            "worktree": {
                "enabled": True,
                "source_cwd": str(root),
                "cwd": str(root / ".worktrees" / "supervisor" / target_name),
            },
        }

    monkeypatch.setattr(
        "isotope.features.supervisor.runner._execute_launch_action",
        stub_execute_launch_action,
    )

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
            "2",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert attempted == ["worker-a", "worker-b"]
    assert payload["executed"]["summary"] == {
        "launched": 1,
        "skipped": 1,
        "limit": 2,
    }
    assert payload["executed"]["results"][0]["managed"]["name"] == "worker-b"
    skipped = payload["executed"]["skipped"]
    assert len(skipped) == 1
    assert skipped[0]["kind"] == "launch_session"
    assert skipped[0]["skipped"] is True
    assert skipped[0]["reason"] == "supervisor action failed"
    assert skipped[0]["error"] == "RuntimeError: boom worker-a"
    assert skipped[0]["failure_event"]["event_type"] == "worker_launch_failed"
    assert skipped[0]["failure_event"]["lane_name"] == "worker-a"
    assert skipped[0]["failure_event"]["retry_count"] == 1


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

    class StubProcess:
        pid = 45682

    def stub_popen(
        command: list[str],
        *,
        cwd: str,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> StubProcess:
        captured["command"] = command
        captured["cwd"] = cwd
        return StubProcess()

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.Popen", stub_popen)

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
    assert (
        loop_payload["supervisor_action"]["target_name"]
        == "supervisor-autopilot-goal-entry"
    )
    assert loop_payload["llm_action"] == loop_payload["supervisor_action"]
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


def test_supervisor_goal_plan_repairs_soft_syntax_output(
    tmp_path,
    capsys,
    monkeypatch,
):
    root = tmp_path / "repo"
    root.mkdir()
    _write_current_docs(root)
    codex_home = tmp_path / ".codex"
    provider = SoftSyntaxRepairGoalProvider()
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
    assert payload["candidates"] == [
        {
            "goal": "模块化 Supervisor。",
            "target_name": "supervisor-modularization",
            "reason": "runner.py 已经过大。",
        }
    ]
    assert payload["parse_repaired"] is True
    assert len(provider.calls) == 2


def test_supervisor_goal_plan_parses_toml_without_repair_llm(
    tmp_path,
    capsys,
    monkeypatch,
):
    root = tmp_path / "repo"
    root.mkdir()
    _write_current_docs(root)
    codex_home = tmp_path / ".codex"
    provider = TomlGoalProvider()
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
    assert provider.calls == 1
    assert payload["parse_repaired"] is False
    assert payload["plan_summary"] == "并行推进三个板块"
    assert [item["target_name"] for item in payload["candidates"]] == [
        "supervisor-modularization",
        "memory-storage-layer",
    ]
    assert payload["parallel_recommendations"] == [
        {
            "batch": "第一批",
            "targets": ["supervisor-modularization", "memory-storage-layer"],
            "reason": "两个目标边界不同",
        }
    ]


def test_supervisor_goal_plan_prompt_allows_toml_but_not_markdown(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    messages = build_goal_planning_messages(
        root=root,
        facts={
            "docs/current/status.md": "状态",
            "docs/current/agent-task-queue.md": "任务",
            "docs/current/supervisor-capability-map.md": "能力",
        },
        user_goal="拆目标",
        limit=3,
        write_mode=False,
    )

    content = messages[1]["content"]
    assert "TOML" in content
    assert "Markdown" not in content


def test_supervisor_goal_plan_prompt_forbids_unstated_provider_claims(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    messages = build_goal_planning_messages(
        root=root,
        facts={
            "docs/current/status.md": "状态",
            "docs/current/agent-task-queue.md": "任务",
            "docs/current/supervisor-capability-map.md": "能力",
        },
        user_goal="验证真实 API 路径",
        limit=3,
        write_mode=False,
    )

    system_prompt = messages[0]["content"]
    assert "provider" in system_prompt
    assert "fake" in system_prompt
    assert "不要猜测" in system_prompt
    assert "除非 user_goal 原文点名 provider/fake" in system_prompt
    assert "不要猜文件路径" in system_prompt


def test_supervisor_goal_plan_redacts_provider_facts_unless_user_asks(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    messages = build_goal_planning_messages(
        root=root,
        facts={
            "docs/current/status.md": "目标规划入口已接入 capacity。\n测试只用 fake provider。",
            "docs/current/agent-task-queue.md": "下一步接 dashboard。",
            "docs/current/supervisor-capability-map.md": "provider 配置背景不该变成任务。",
        },
        user_goal="验证 dashboard 目标规划入口真实可用",
        limit=3,
        write_mode=False,
    )

    user_payload = json.loads(messages[1]["content"])
    serialized_facts = json.dumps(user_payload["facts"], ensure_ascii=False).lower()
    assert "fake" not in serialized_facts
    assert "provider" not in serialized_facts
    assert "目标规划入口已接入 capacity" in serialized_facts
    assert "下一步接 dashboard" in serialized_facts


def test_supervisor_goal_plan_keeps_provider_facts_when_user_asks(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    messages = build_goal_planning_messages(
        root=root,
        facts={
            "docs/current/status.md": "测试只用 fake provider。",
            "docs/current/agent-task-queue.md": "下一步接 dashboard。",
        },
        user_goal="检查 provider 配置",
        limit=3,
        write_mode=False,
    )

    user_payload = json.loads(messages[1]["content"])
    serialized_facts = json.dumps(user_payload["facts"], ensure_ascii=False).lower()
    assert "fake provider" in serialized_facts


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
