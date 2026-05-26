from types import SimpleNamespace

from isotope.features.supervisor.state.fanout import (
    build_fanout_launch_plan,
    build_fanout_status_summary,
)
from isotope.features.supervisor.runner import _execute_fanout_launch_actions


def test_supervisor_fanout_turns_parallel_recommendations_into_launch_specs():
    goal_plan = {
        "root": "/repo/isotope",
        "candidates": [
            {
                "goal": "实现状态按钮的前端刷新。",
                "target_name": "supervisor-status-buttons",
                "reason": "状态按钮和 hosted output 写入区域不同。",
            },
            {
                "goal": "实现 hosted output 展示。",
                "target_name": "supervisor-hosted-output",
                "reason": "状态按钮和 hosted output 写入区域不同。",
            },
        ],
        "parallel_recommendations": [
            {
                "batch": "并行批次",
                "targets": [
                    "supervisor-status-buttons",
                    "supervisor-hosted-output",
                ],
                "reason": "两个目标可由不同 worker 并行。",
            }
        ],
    }

    plan = build_fanout_launch_plan(goal_plan)

    assert plan["status"] == "ok"
    assert plan["summary"] == {"launchable": 2, "skipped": 0, "limit": 3}
    assert plan["launch_specs"] == [
        {
            "kind": "launch_session",
            "target_name": "supervisor-status-buttons",
            "cwd": "/repo/isotope",
            "prompt": "实现状态按钮的前端刷新。",
            "reason": "两个目标可由不同 worker 并行。",
            "batch": "并行批次",
            "source": "parallel_recommendations",
            "candidate_reason": "状态按钮和 hosted output 写入区域不同。",
            "review": {
                "requires_human_review": True,
                "note": "fanout 只生成受控 launch spec；runner 执行时仍需通过 launch gate。",
            },
        },
        {
            "kind": "launch_session",
            "target_name": "supervisor-hosted-output",
            "cwd": "/repo/isotope",
            "prompt": "实现 hosted output 展示。",
            "reason": "两个目标可由不同 worker 并行。",
            "batch": "并行批次",
            "source": "parallel_recommendations",
            "candidate_reason": "状态按钮和 hosted output 写入区域不同。",
            "review": {
                "requires_human_review": True,
                "note": "fanout 只生成受控 launch spec；runner 执行时仍需通过 launch gate。",
            },
        },
    ]
    assert plan["skipped"] == []


def test_supervisor_fanout_dedupes_caps_and_skips_running_workers():
    goal_plan = {
        "root": "/repo/isotope",
        "candidates": [
            {
                "goal": "实现 worker A。",
                "target_name": "worker-a",
                "reason": "A 可并行。",
            },
            {
                "goal": "实现 worker B。",
                "target_name": "worker-b",
                "reason": "B 可并行。",
            },
            {
                "goal": "实现 worker C。",
                "target_name": "worker-c",
                "reason": "C 可并行。",
            },
        ],
        "parallel_recommendations": [
            {
                "batch": "批次 1",
                "targets": ["worker-a", "worker-a", "worker-b", "worker-c"],
                "reason": "第一批。",
            },
            {
                "batch": "批次 2",
                "targets": ["missing-worker"],
                "reason": "目标缺失。",
            },
        ],
    }

    plan = build_fanout_launch_plan(
        goal_plan,
        limit=1,
        running_target_names={"worker-b"},
    )

    assert plan["summary"] == {"launchable": 0, "skipped": 5, "limit": 1}
    assert plan["launch_specs"] == []
    assert plan["skipped"] == [
        {
            "target_name": "worker-a",
            "reason": "global_running_limit_reached",
            "batch": "批次 1",
        },
        {
            "target_name": "worker-a",
            "reason": "duplicate_target",
            "batch": "批次 1",
        },
        {
            "target_name": "worker-b",
            "reason": "worker_already_running",
            "batch": "批次 1",
        },
        {
            "target_name": "worker-c",
            "reason": "global_running_limit_reached",
            "batch": "批次 1",
        },
        {
            "target_name": "missing-worker",
            "reason": "candidate_not_found",
            "batch": "批次 2",
        },
    ]


def test_supervisor_fanout_can_use_written_goals_and_explicit_cwd():
    goal_plan = {
        "written_goals": [
            {
                "goal": "补 daemon 状态汇总。",
                "target_name": "daemon-status-summary",
                "cwd": "/repo/worker",
                "reason": "写入目标队列后可启动。",
            }
        ],
        "parallel_recommendations": [
            {
                "targets": ["daemon-status-summary"],
                "reason": "只有一个 worker 也保持统一 fanout contract。",
            }
        ],
    }

    plan = build_fanout_launch_plan(goal_plan, cwd="/repo/fallback")

    assert plan["launch_specs"][0]["cwd"] == "/repo/worker"
    assert plan["launch_specs"][0]["prompt"] == "补 daemon 状态汇总。"


def test_supervisor_fanout_status_summarizes_completed_batch():
    summary = build_fanout_status_summary(
        active_goals=[],
        goal_updates=[
            {
                "goal_id": "goal-a",
                "target_name": "worker-a",
                "status": "done",
                "summary": "A 已完成。",
                "next": "等待归档。",
            },
            {
                "goal_id": "goal-b",
                "target_name": "worker-b",
                "status": "done",
                "summary": "B 已完成。",
                "next": "等待归档。",
            },
        ],
    )

    assert summary == {
        "status": "completed",
        "summary": {
            "total": 2,
            "done": 2,
            "blocked": 0,
            "needs_user": 0,
            "running": 0,
            "pending": 0,
        },
        "message": "fanout batch completed: 2 workers done.",
        "results": [
            {
                "goal_id": "goal-a",
                "target_name": "worker-a",
                "status": "done",
                "summary": "A 已完成。",
                "next": "等待归档。",
            },
            {
                "goal_id": "goal-b",
                "target_name": "worker-b",
                "status": "done",
                "summary": "B 已完成。",
                "next": "等待归档。",
            },
        ],
        "requires_user_attention": False,
    }


def test_supervisor_fanout_status_pauses_on_blocked_worker():
    summary = build_fanout_status_summary(
        active_goals=[
            {
                "goal_id": "goal-a",
                "target_name": "worker-a",
                "goal": "继续 A。",
                "last_status": "blocked",
                "last_summary": "A 缺少依赖。",
                "last_next": "等待依赖恢复。",
            },
            {
                "goal_id": "goal-b",
                "target_name": "worker-b",
                "goal": "继续 B。",
            },
        ],
        goal_updates=[],
        running_target_names={"worker-b"},
    )

    assert summary["status"] == "paused"
    assert summary["requires_user_attention"] is True
    assert summary["summary"] == {
        "total": 2,
        "done": 0,
        "blocked": 1,
        "needs_user": 0,
        "running": 1,
        "pending": 0,
    }
    assert summary["attention"] == [
        {
            "goal_id": "goal-a",
            "target_name": "worker-a",
            "status": "blocked",
            "summary": "A 缺少依赖。",
            "next": "等待依赖恢复。",
        }
    ]


def test_supervisor_fanout_execution_dedupes_duplicate_launch_specs(
    tmp_path,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
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
        return FakeProcess(47100 + len(captured))

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.subprocess.Popen",
        fake_popen,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner._pid_is_running",
        lambda _: False,
        raising=False,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner._prepare_launch_worktree",
        lambda *, cwd, target_name: {"cwd": str(cwd), "branch": target_name},
    )

    args = SimpleNamespace(
        codex_home=str(codex_home),
        max_run_minutes=0,
        prompt_cooldown=0,
        worker_profile="coding",
        worker_codex_model="gpt-5.5",
        worker_codex_config=('model_reasoning_effort="high"',),
    )
    fanout_plan = {
        "summary": {"limit": 3},
        "launch_specs": [
            {
                "kind": "launch_session",
                "target_name": "worker-a",
                "cwd": str(workspace),
                "prompt": "实现 worker A。",
            },
            {
                "kind": "launch_session",
                "target_name": "worker-a",
                "cwd": str(workspace),
                "prompt": "重复的 worker A。",
            },
        ],
    }

    executed = _execute_fanout_launch_actions(args, fanout_plan)

    assert executed["summary"] == {"launched": 1, "skipped": 1, "limit": 3}
    assert executed["results"][0]["managed"]["name"] == "worker-a"
    assert executed["skipped"] == [
        {
            "kind": "launch_session",
            "skipped": True,
            "reason": "duplicate_fanout_target",
            "target_name": "worker-a",
        }
    ]
    assert len(captured) == 1
