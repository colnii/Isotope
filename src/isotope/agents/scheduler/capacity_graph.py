"""Capacity graph planning on top of the pure dependency graph."""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .dependency_graph import (
    DependencyGraph,
    DependencyGraphError,
    GraphNode,
    NodeState,
    build_dependency_graph,
    resolve_ready_nodes,
)


CapacityNodeState = NodeState


@dataclass(frozen=True)
class CapacityGraphNode:
    node_id: str
    capacity_id: str
    arguments: Mapping[str, Any] = field(default_factory=dict)
    depends_on: tuple[str, ...] = ()
    stage: str | None = None
    scope: str | None = None
    merge_gate: bool = True

    def __post_init__(self) -> None:
        node_id = self.node_id.strip()
        capacity_id = self.capacity_id.strip()
        if not node_id:
            raise ValueError("node_id must not be empty")
        if not capacity_id:
            raise ValueError("capacity_id must not be empty")
        object.__setattr__(self, "node_id", node_id)
        object.__setattr__(self, "capacity_id", capacity_id)
        object.__setattr__(self, "arguments", dict(self.arguments))
        object.__setattr__(self, "depends_on", tuple(self.depends_on))


@dataclass(frozen=True)
class CapacityGraph:
    nodes: tuple[CapacityGraphNode, ...]
    dependency_graph: DependencyGraph
    node_by_id: dict[str, CapacityGraphNode]


@dataclass(frozen=True)
class CapacityCallPlan:
    node_id: str
    capacity_id: str
    arguments: dict[str, Any]
    dependency_graph: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "capacity_call_plan",
            "node_id": self.node_id,
            "capacity_id": self.capacity_id,
            "arguments": copy.deepcopy(self.arguments),
            "dependency_graph": copy.deepcopy(self.dependency_graph),
        }


@dataclass(frozen=True)
class CapacityGraphPlan:
    status: str
    calls: list[CapacityCallPlan]
    blocked: list[dict[str, str]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "capacity_graph_plan",
            "status": self.status,
            "summary": {
                "ready": len(self.calls),
                "blocked": len(self.blocked),
            },
            "calls": [call.to_dict() for call in self.calls],
            "blocked": copy.deepcopy(self.blocked),
        }


def build_capacity_graph(nodes: Sequence[CapacityGraphNode]) -> CapacityGraph:
    node_tuple = tuple(nodes)
    dependency_graph = build_dependency_graph(
        [
            GraphNode(
                node.node_id,
                depends_on=node.depends_on,
                stage=node.stage,
                scope=node.scope,
                merge_gate=node.merge_gate,
            )
            for node in node_tuple
        ]
    )
    return CapacityGraph(
        nodes=node_tuple,
        dependency_graph=dependency_graph,
        node_by_id={node.node_id: node for node in node_tuple},
    )


def capacity_graph_node_from_call_selection(
    selection: Mapping[str, Any] | Any,
    *,
    node_id: str | None = None,
    depends_on: tuple[str, ...] = (),
    stage: str | None = None,
    scope: str | None = None,
    merge_gate: bool = True,
) -> CapacityGraphNode:
    payload = _selection_payload(selection)
    status = _required_string(payload.get("status"), "status")
    if status != "ready_to_call":
        raise ValueError(f"capacity selection is not ready_to_call: {status}")
    capacity_id = _required_string(payload.get("capacity_id"), "capacity_id")
    arguments = payload.get("arguments")
    if not isinstance(arguments, Mapping):
        raise ValueError("capacity selection arguments must be a mapping")
    return CapacityGraphNode(
        node_id=node_id or _default_node_id(capacity_id),
        capacity_id=capacity_id,
        arguments=dict(arguments),
        depends_on=depends_on,
        stage=stage,
        scope=scope,
        merge_gate=merge_gate,
    )


def resolve_ready_capacity_plan(
    graph: CapacityGraph,
    *,
    states: Mapping[str, CapacityNodeState],
) -> CapacityGraphPlan:
    try:
        ready_nodes = resolve_ready_nodes(graph.dependency_graph, states=states)
    except DependencyGraphError as exc:
        return CapacityGraphPlan(
            status="blocked",
            calls=[],
            blocked=[
                {
                    "node_id": node.node_id,
                    "capacity_id": node.capacity_id,
                    "reason": "dependency_graph_invalid",
                    "detail": str(exc),
                }
                for node in graph.nodes
            ],
        )

    ready_ids = {node.node_id for node in ready_nodes}
    calls = [
        _capacity_call_plan(node)
        for node in graph.nodes
        if node.node_id in ready_ids
    ]
    blocked = [
        {
            "node_id": node.node_id,
            "capacity_id": node.capacity_id,
            "reason": "not_ready",
        }
        for node in graph.nodes
        if node.node_id not in ready_ids
    ]
    return CapacityGraphPlan(
        status="ready" if calls else "blocked",
        calls=calls,
        blocked=blocked,
    )


def _capacity_call_plan(node: CapacityGraphNode) -> CapacityCallPlan:
    return CapacityCallPlan(
        node_id=node.node_id,
        capacity_id=node.capacity_id,
        arguments=copy.deepcopy(dict(node.arguments)),
        dependency_graph=_node_dependency_summary(node),
    )


def _node_dependency_summary(node: CapacityGraphNode) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    if node.depends_on:
        summary["depends_on"] = list(node.depends_on)
    if node.stage is not None:
        summary["stage"] = node.stage
    if node.scope is not None:
        summary["scope"] = node.scope
    if not node.merge_gate:
        summary["merge_gate"] = False
    return summary


def _selection_payload(selection: Mapping[str, Any] | Any) -> Mapping[str, Any]:
    if isinstance(selection, Mapping):
        return selection
    to_dict = getattr(selection, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
        if isinstance(payload, Mapping):
            return payload
    raise ValueError("capacity selection must be a mapping or expose to_dict()")


def _required_string(value: Any, field_name: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise ValueError(f"capacity selection {field_name} must be a non-empty string")


def _default_node_id(capacity_id: str) -> str:
    return capacity_id.replace(".", "-")
