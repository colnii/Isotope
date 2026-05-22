"""Pure dependency graph helpers for agent scheduler goals."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal


NodeStatus = Literal["pending", "running", "done", "blocked", "needs_user", "failed"]


class DependencyGraphError(ValueError):
    """Raised when a dependency graph cannot be scheduled safely."""


@dataclass(frozen=True)
class GraphNode:
    node_id: str
    depends_on: tuple[str, ...] = ()
    stage: str | None = None
    scope: str | None = None
    merge_gate: bool = True

    def __post_init__(self) -> None:
        node_id = self.node_id.strip()
        if not node_id:
            raise DependencyGraphError("node_id must not be empty")
        object.__setattr__(self, "node_id", node_id)
        object.__setattr__(self, "depends_on", tuple(self.depends_on))


@dataclass(frozen=True)
class NodeState:
    status: NodeStatus = "pending"
    merged: bool = False
    verified: bool = False


@dataclass(frozen=True)
class DependencyGraph:
    nodes: tuple[GraphNode, ...]
    node_by_id: dict[str, GraphNode] = field(default_factory=dict)


def build_dependency_graph(nodes: Sequence[GraphNode]) -> DependencyGraph:
    node_tuple = tuple(nodes)
    return DependencyGraph(node_tuple, {node.node_id: node for node in node_tuple})


def build_dependency_graph_from_goal_records(
    goals: Iterable[Mapping[str, Any]],
) -> DependencyGraph:
    nodes = [
        GraphNode(
            _goal_node_id(goal),
            depends_on=_string_tuple(goal.get("depends_on")),
            stage=_optional_string(goal.get("stage")),
            scope=_optional_string(goal.get("scope")),
            merge_gate=bool(goal.get("merge_gate", True)),
        )
        for goal in goals
    ]
    return build_dependency_graph(nodes)


def build_node_states_from_goal_records(
    goals: Iterable[Mapping[str, Any]],
) -> dict[str, NodeState]:
    states: dict[str, NodeState] = {}
    for goal in goals:
        status = _node_status(goal.get("last_status") or goal.get("status"))
        if status == "pending" and not (
            bool(goal.get("merged")) or bool(goal.get("verified"))
        ):
            continue
        states[_goal_node_id(goal)] = NodeState(
            status=status,
            merged=bool(goal.get("merged")),
            verified=bool(goal.get("verified")),
        )
    return states


def validate_dependency_graph(graph: DependencyGraph) -> None:
    if len(graph.node_by_id) != len(graph.nodes):
        raise DependencyGraphError("duplicate node_id in dependency graph")
    for node in graph.nodes:
        for dependency_id in node.depends_on:
            if dependency_id not in graph.node_by_id:
                raise DependencyGraphError(
                    f"missing dependency {dependency_id!r} for node {node.node_id!r}"
                )
    _raise_for_cycles(graph)


def resolve_ready_nodes(
    graph: DependencyGraph,
    *,
    states: Mapping[str, NodeState],
) -> list[GraphNode]:
    validate_dependency_graph(graph)
    return [
        node
        for node in graph.nodes
        if _node_is_pending(node, states=states)
        and _dependencies_are_satisfied(node, states=states)
    ]


def _node_is_pending(node: GraphNode, *, states: Mapping[str, NodeState]) -> bool:
    state = states.get(node.node_id)
    return state is None or state.status == "pending"


def _dependencies_are_satisfied(
    node: GraphNode,
    *,
    states: Mapping[str, NodeState],
) -> bool:
    for dependency_id in node.depends_on:
        dependency_state = states.get(dependency_id)
        if dependency_state is None or dependency_state.status != "done":
            return False
        if node.merge_gate and (
            not dependency_state.merged or not dependency_state.verified
        ):
            return False
    return True


def _raise_for_cycles(graph: DependencyGraph) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str, path: tuple[str, ...]) -> None:
        if node_id in visited:
            return
        if node_id in visiting:
            cycle_path = " -> ".join((*path, node_id))
            raise DependencyGraphError(f"cycle detected: {cycle_path}")
        visiting.add(node_id)
        node = graph.node_by_id[node_id]
        for dependency_id in node.depends_on:
            visit(dependency_id, (*path, node_id))
        visiting.remove(node_id)
        visited.add(node_id)

    for node in graph.nodes:
        visit(node.node_id, ())


def _goal_node_id(goal: Mapping[str, Any]) -> str:
    for key in ("target_name", "goal_id", "id"):
        value = _optional_string(goal.get(key))
        if value is not None:
            return value
    raise DependencyGraphError("goal record must include target_name, goal_id, or id")


def _string_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(
        item.strip() for item in value if isinstance(item, str) and item.strip()
    )


def _optional_string(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _node_status(value: Any) -> NodeStatus:
    if isinstance(value, str) and value in {
        "pending",
        "running",
        "done",
        "blocked",
        "needs_user",
        "failed",
    }:
        return value
    return "pending"
