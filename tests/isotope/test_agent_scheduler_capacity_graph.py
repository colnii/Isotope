from isotope.agents.scheduler.capacity_graph import (
    CapacityGraph,
    CapacityGraphNode,
    CapacityNodeState,
    build_capacity_graph,
    resolve_ready_capacity_plan,
)
from isotope.agents.scheduler.dependency_graph import DependencyGraph


def test_capacity_graph_resolves_ready_capacity_plans_without_executing_them():
    graph = build_capacity_graph(
        [
            CapacityGraphNode(
                "retrieve-context",
                capacity_id="context.search",
                arguments={"query": "scheduler dependency graph"},
                stage="context",
            ),
            CapacityGraphNode(
                "review-artifact",
                capacity_id="artifact.review",
                arguments={"artifact_id": "artifact-123"},
                depends_on=("retrieve-context",),
                stage="review",
            ),
        ]
    )

    plan = resolve_ready_capacity_plan(graph, states={})

    assert plan.status == "ready"
    assert [call.node_id for call in plan.calls] == ["retrieve-context"]
    assert plan.calls[0].capacity_id == "context.search"
    assert plan.calls[0].arguments == {"query": "scheduler dependency graph"}
    assert plan.calls[0].dependency_graph == {"stage": "context"}
    assert plan.to_dict()["calls"][0]["kind"] == "capacity_call_plan"


def test_capacity_graph_unlocks_downstream_after_dependency_gate_is_satisfied():
    graph = build_capacity_graph(
        [
            CapacityGraphNode("retrieve-context", capacity_id="context.search"),
            CapacityGraphNode(
                "review-artifact",
                capacity_id="artifact.review",
                depends_on=("retrieve-context",),
            ),
        ]
    )

    plan = resolve_ready_capacity_plan(
        graph,
        states={
            "retrieve-context": CapacityNodeState(
                status="done",
                merged=True,
                verified=True,
            )
        },
    )

    assert [call.node_id for call in plan.calls] == ["review-artifact"]
    assert plan.to_dict()["summary"] == {"ready": 1, "blocked": 1}


def test_capacity_graph_reports_invalid_dependency_graph_as_blocked_plan():
    graph = build_capacity_graph(
        [
            CapacityGraphNode(
                "review-artifact",
                capacity_id="artifact.review",
                depends_on=("missing-context",),
            )
        ]
    )

    plan = resolve_ready_capacity_plan(graph, states={})

    assert plan.status == "blocked"
    assert plan.calls == []
    assert plan.blocked == [
        {
            "node_id": "review-artifact",
            "capacity_id": "artifact.review",
            "reason": "dependency_graph_invalid",
            "detail": "missing dependency 'missing-context' for node 'review-artifact'",
        }
    ]


def test_capacity_graph_composes_dependency_graph_and_does_not_define_executor():
    graph = build_capacity_graph(
        [
            CapacityGraphNode(
                "review-artifact",
                capacity_id="artifact.review",
                arguments={"artifact_id": "artifact-123"},
                scope="artifact",
                merge_gate=False,
            )
        ]
    )

    plan = resolve_ready_capacity_plan(graph, states={})
    payload = plan.to_dict()["calls"][0]

    assert isinstance(graph, CapacityGraph)
    assert isinstance(graph.dependency_graph, DependencyGraph)
    assert not isinstance(graph, DependencyGraph)
    assert payload["dependency_graph"] == {
        "scope": "artifact",
        "merge_gate": False,
    }
    assert "executor" not in payload
