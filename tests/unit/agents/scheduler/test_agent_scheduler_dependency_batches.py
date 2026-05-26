from isotope.agents.scheduler.dependency_batches import build_dependency_batch_plan


def test_dependency_batch_plan_unlocks_only_merged_and_verified_dependencies():
    goals = [
        {
            "target_name": "foundation-a",
            "stage": "foundation",
            "last_status": "done",
            "merged": True,
            "verified": True,
        },
        {
            "target_name": "foundation-b",
            "stage": "foundation",
            "last_status": "done",
            "merged": True,
            "verified": False,
        },
        {
            "target_name": "wire-a",
            "stage": "wire",
            "depends_on": ["foundation-a"],
        },
        {
            "target_name": "wire-b",
            "stage": "wire",
            "depends_on": ["foundation-b"],
        },
    ]

    plan = build_dependency_batch_plan(goals, limit=2)

    assert plan["status"] == "ready"
    assert [item["target_name"] for item in plan["ready_goals"]] == ["wire-a"]
    assert plan["blocked_goals"] == [
        {
            "target_name": "wire-b",
            "reason": "dependency_unmet",
            "dependency": "foundation-b",
        }
    ]
    assert plan["summary"] == {
        "ready": 1,
        "blocked": 1,
        "running": 0,
        "attention": 0,
        "limit": 2,
    }


def test_dependency_batch_plan_pauses_when_dependency_needs_attention():
    goals = [
        {
            "target_name": "foundation-a",
            "stage": "foundation",
            "last_status": "needs_user",
        },
        {
            "target_name": "wire-a",
            "stage": "wire",
            "depends_on": ["foundation-a"],
        },
    ]

    plan = build_dependency_batch_plan(goals, limit=2)

    assert plan["status"] == "paused"
    assert plan["ready_goals"] == []
    assert plan["attention_goals"] == [
        {"target_name": "foundation-a", "status": "needs_user"}
    ]
    assert plan["blocked_goals"] == [
        {
            "target_name": "wire-a",
            "reason": "dependency_attention",
            "dependency": "foundation-a",
        }
    ]


def test_dependency_batch_plan_counts_running_workers_against_limit():
    goals = [
        {"target_name": "worker-a", "stage": "foundation"},
        {"target_name": "worker-b", "stage": "foundation"},
        {"target_name": "worker-c", "stage": "foundation"},
    ]

    plan = build_dependency_batch_plan(
        goals,
        limit=2,
        running_target_names={"worker-a"},
    )

    assert plan["status"] == "ready"
    assert [item["target_name"] for item in plan["ready_goals"]] == ["worker-b"]
    assert plan["blocked_goals"] == [
        {
            "target_name": "worker-c",
            "reason": "global_running_limit_reached",
        }
    ]
    assert plan["summary"]["running"] == 1
