from isotope.features.supervisor.fanout import build_fanout_launch_plan


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

    assert plan["summary"] == {"launchable": 1, "skipped": 4, "limit": 1}
    assert [item["target_name"] for item in plan["launch_specs"]] == ["worker-a"]
    assert plan["skipped"] == [
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
            "reason": "fanout_limit_reached",
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
