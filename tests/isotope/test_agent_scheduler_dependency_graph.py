import pytest

from isotope.agents.scheduler.dependency_graph import (
    DependencyGraphError,
    GraphNode,
    NodeState,
    build_dependency_graph_from_goal_records,
    build_dependency_graph,
    build_node_states_from_goal_records,
    resolve_ready_nodes,
    validate_dependency_graph,
)


def test_dependency_graph_resolves_parallel_roots_before_downstream_nodes():
    graph = build_dependency_graph(
        [
            GraphNode("worker-a", stage="extract", scope="codex-session-reader"),
            GraphNode("worker-b", stage="extract", scope="decision-ledger"),
            GraphNode("worker-c", stage="wire", depends_on=("worker-a", "worker-b")),
        ]
    )

    ready = resolve_ready_nodes(graph, states={})

    assert [node.node_id for node in ready] == ["worker-a", "worker-b"]


def test_dependency_graph_unlocks_downstream_after_dependencies_are_merged_and_verified():
    graph = build_dependency_graph(
        [
            GraphNode("worker-a"),
            GraphNode("worker-b"),
            GraphNode("worker-c", depends_on=("worker-a", "worker-b")),
        ]
    )

    ready = resolve_ready_nodes(
        graph,
        states={
            "worker-a": NodeState(status="done", merged=True, verified=True),
            "worker-b": NodeState(status="done", merged=True, verified=True),
        },
    )

    assert [node.node_id for node in ready] == ["worker-c"]


def test_dependency_graph_blocks_downstream_when_dependency_needs_attention():
    graph = build_dependency_graph(
        [
            GraphNode("worker-a"),
            GraphNode("worker-b", depends_on=("worker-a",)),
        ]
    )

    ready = resolve_ready_nodes(
        graph,
        states={"worker-a": NodeState(status="needs_user")},
    )

    assert ready == []


def test_dependency_graph_rejects_missing_dependencies_and_cycles():
    with pytest.raises(DependencyGraphError, match="missing dependency"):
        validate_dependency_graph(
            build_dependency_graph([GraphNode("worker-a", depends_on=("missing",))])
        )

    with pytest.raises(DependencyGraphError, match="cycle"):
        validate_dependency_graph(
            build_dependency_graph(
                [
                    GraphNode("worker-a", depends_on=("worker-b",)),
                    GraphNode("worker-b", depends_on=("worker-a",)),
                ]
            )
        )


def test_dependency_graph_builds_from_supervisor_goal_records():
    goals = [
        {
            "goal_id": "goal-a",
            "target_name": "worker-a",
            "last_status": "done",
            "merged": True,
            "verified": True,
        },
        {
            "goal_id": "goal-b",
            "target_name": "worker-b",
            "last_status": "done",
            "merged": True,
            "verified": True,
        },
        {
            "goal_id": "goal-c",
            "target_name": "worker-c",
            "depends_on": ["worker-a", "worker-b"],
            "stage": "wire",
            "scope": "agents/scheduler",
        },
    ]

    graph = build_dependency_graph_from_goal_records(goals)
    states = build_node_states_from_goal_records(goals)
    ready = resolve_ready_nodes(graph, states=states)

    assert [node.node_id for node in ready] == ["worker-c"]
    assert ready[0].stage == "wire"
    assert ready[0].scope == "agents/scheduler"


def test_dependency_graph_can_skip_merge_gate_for_local_non_git_steps():
    graph = build_dependency_graph(
        [
            GraphNode("read-docs"),
            GraphNode("write-plan", depends_on=("read-docs",), merge_gate=False),
        ]
    )

    ready = resolve_ready_nodes(
        graph,
        states={"read-docs": NodeState(status="done")},
    )

    assert [node.node_id for node in ready] == ["write-plan"]
