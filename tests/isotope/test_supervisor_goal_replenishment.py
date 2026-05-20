from __future__ import annotations

import json
import sys
from pathlib import Path

from isotope.features.supervisor.goal_queue import read_active_supervisor_goals
from isotope.features.supervisor.runner import main as supervisor_main


class LowWaterGoalProvider:
    def __init__(self) -> None:
        self.payloads: list[dict[str, object]] = []

    def summarize(self, messages: list[dict[str, str]]) -> str:
        payload = json.loads(messages[1]["content"])
        self.payloads.append(payload)
        assert payload["planning_trigger"] == "low_water"
        assert payload["goal_count_limit"] == 2
        assert "docs/current/status.md" in payload["facts"]
        assert "docs/current/agent-task-queue.md" in payload["facts"]
        assert "docs/current/supervisor-capability-map.md" in payload["facts"]
        return json.dumps(
            {
                "plan_summary": "继续推进 Supervisor 过夜自动开发闭环。",
                "goals": [
                    {
                        "goal": "补齐低水位补任务的 loop 验收。",
                        "target_name": "supervisor-low-water-loop",
                        "reason": "当前文档要求 Supervisor 能持续安排任务。",
                    },
                    {
                        "goal": "补齐低水位补任务的 daemon 参数透传。",
                        "target_name": "supervisor-low-water-daemon",
                        "reason": "后台长跑必须保留低水位配置。",
                    },
                ],
            },
            ensure_ascii=False,
        )


class BrokenGoalProvider:
    def summarize(self, messages: list[dict[str, str]]) -> str:
        raise RuntimeError("provider unavailable")


class ThreeGoalProvider:
    def summarize(self, messages: list[dict[str, str]]) -> str:
        payload = json.loads(messages[1]["content"])
        assert payload["planning_trigger"] == "low_water"
        assert payload["goal_count_limit"] == 3
        return json.dumps(
            {
                "plan_summary": "低水位一次补三条任务。",
                "goals": [
                    {
                        "goal": "实现低水位 fanout 目标 A。",
                        "target_name": "low-water-fanout-a",
                        "reason": "A 可独立验证。",
                    },
                    {
                        "goal": "实现低水位 fanout 目标 B。",
                        "target_name": "low-water-fanout-b",
                        "reason": "B 可独立验证。",
                    },
                    {
                        "goal": "实现低水位 fanout 目标 C。",
                        "target_name": "low-water-fanout-c",
                        "reason": "C 可独立验证。",
                    },
                ],
            },
            ensure_ascii=False,
        )


def _write_current_docs(root: Path) -> None:
    current = root / "docs" / "current"
    current.mkdir(parents=True)
    (current / "status.md").write_text(
        "Supervisor 正在从手动派发走向低水位自动补任务。\n",
        encoding="utf-8",
    )
    (current / "agent-task-queue.md").write_text(
        "- 下一步：让 loop 根据文档补充 active goals。\n",
        encoding="utf-8",
    )
    (current / "supervisor-capability-map.md").write_text(
        "- goal plan 可以把 LLM 规划写入 goal queue。\n",
        encoding="utf-8",
    )


def test_supervisor_loop_replenishes_goals_from_docs_when_low_water(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_current_docs(workspace)
    provider = LowWaterGoalProvider()
    captured: list[list[str]] = []
    running_pids: set[int] = set()

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
        pid = 47000 + len(captured)
        running_pids.add(pid)
        return FakeProcess(pid)

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: provider,
    )
    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.Popen", fake_popen)
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._pid_is_running",
        lambda pid: pid in running_pids,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner._pid_is_running",
        lambda pid: pid in running_pids,
        raising=False,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._git_branch_for",
        lambda cwd: None,
    )

    exit_code = supervisor_main(
        [
            "loop",
            "--codex-home",
            str(codex_home),
            "--workspace-root",
            str(workspace),
            "--goal-low-water",
            "2",
            "--goal-replenish-limit",
            "2",
            "--iterations",
            "1",
            "--interval",
            "1",
            "--no-auto-adopt",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["goal_replenishment"]["status"] == "ok"
    assert payload["goal_replenishment"]["active_before"] == 0
    assert payload["goal_replenishment"]["written_count"] == 2
    assert [goal["target_name"] for goal in payload["active_goals"]] == [
        "supervisor-low-water-loop",
        "supervisor-low-water-daemon",
    ]
    assert payload["llm_action"]["kind"] == "fanout_launch_sessions"
    assert payload["executed"]["summary"]["launched"] == 2
    assert len(captured) == 2
    assert read_active_supervisor_goals(codex_home=codex_home)


def test_low_water_fanout_respects_launch_limit_and_logs_trigger(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_current_docs(workspace)
    captured: list[list[str]] = []
    running_pids: set[int] = set()

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
        pid = 48000 + len(captured)
        running_pids.add(pid)
        return FakeProcess(pid)

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: ThreeGoalProvider(),
    )
    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.Popen", fake_popen)
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._pid_is_running",
        lambda pid: pid in running_pids,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner._pid_is_running",
        lambda pid: pid in running_pids,
        raising=False,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._git_branch_for",
        lambda cwd: None,
    )

    exit_code = supervisor_main(
        [
            "loop",
            "--codex-home",
            str(codex_home),
            "--workspace-root",
            str(workspace),
            "--goal-low-water",
            "3",
            "--goal-replenish-limit",
            "3",
            "--max-fanout-launches",
            "2",
            "--iterations",
            "1",
            "--interval",
            "1",
            "--no-auto-adopt",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["goal_replenishment"]["written_count"] == 3
    assert payload["fanout_plan"]["summary"] == {
        "launchable": 2,
        "skipped": 1,
        "limit": 2,
    }
    assert payload["executed"]["summary"] == {
        "launched": 2,
        "skipped": 0,
        "limit": 2,
    }
    assert payload["fanout_log"] == {
        "status": "executed",
        "trigger": "low_water",
        "planned_launches": 2,
        "planned_skips": 1,
        "executed_launches": 2,
        "executed_skips": 0,
        "limit": 2,
    }
    assert len(captured) == 2


def test_supervisor_loop_reports_low_water_goal_planning_errors_without_crashing(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_current_docs(workspace)
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: BrokenGoalProvider(),
    )

    exit_code = supervisor_main(
        [
            "loop",
            "--codex-home",
            str(codex_home),
            "--workspace-root",
            str(workspace),
            "--goal-low-water",
            "1",
            "--iterations",
            "1",
            "--interval",
            "1",
            "--no-auto-adopt",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["goal_replenishment"]["status"] == "error"
    assert payload["goal_replenishment"]["active_before"] == 0
    assert "provider unavailable" in payload["goal_replenishment"]["reason"]
    assert payload["active_goals"] == []


def test_supervisor_daemon_start_passes_goal_replenishment_options_to_loop(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    captured: dict[str, object] = {}

    class FakeProcess:
        pid = 47010

    def fake_popen(
        command: list[str],
        *,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> FakeProcess:
        captured["command"] = command
        return FakeProcess()

    monkeypatch.setattr(
        "isotope.features.supervisor.daemon.subprocess.Popen",
        fake_popen,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.daemon._process_is_alive",
        lambda _: False,
    )

    exit_code = supervisor_main(
        [
            "daemon",
            "start",
            "--codex-home",
            str(codex_home),
            "--interval",
            "7",
            "--limit",
            "3",
            "--goal-low-water",
            "2",
            "--goal-replenish-limit",
            "4",
            "--goal-replenish-prompt",
            "根据 current 文档继续补 Supervisor 任务。",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["daemon"]["command"] == [
        sys.executable,
        "-u",
        "-m",
        "isotope.features.supervisor.runner",
        "loop",
        "--codex-home",
        str(codex_home),
        "--interval",
        "7",
        "--limit",
        "3",
        "--goal-low-water",
        "2",
        "--goal-replenish-limit",
        "4",
        "--goal-replenish-prompt",
        "根据 current 文档继续补 Supervisor 任务。",
        "--worker-codex-model",
        "gpt-5.5",
        "--worker-codex-config",
        'model_reasoning_effort="high"',
    ]
    assert captured["command"] == payload["daemon"]["command"]
