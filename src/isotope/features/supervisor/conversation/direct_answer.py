"""Direct-answer protocol validation for Supervisor conversation decisions."""

from __future__ import annotations

from typing import Any


def direct_answer_rejection_observation(
    decision: dict[str, Any],
    *,
    observations: list[dict[str, Any]],
) -> dict[str, Any] | None:
    basis = decision.get("answer_basis")
    capacity_observations = _capacity_observations(observations)
    if capacity_observations:
        return _observation_basis_rejection(
            basis,
            observations=capacity_observations,
        )
    if _basis_kind(basis) == "no_capability_needed":
        return None
    return _invalid_direct_answer_observation(
        reason="direct_answer before any capacity observation requires answer_basis.kind=no_capability_needed",
        decision=decision,
    )


def _observation_basis_rejection(
    basis: Any,
    *,
    observations: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if _basis_kind(basis) != "observation":
        return None
    cited_capacity_ids = _basis_capacity_ids(basis)
    if not cited_capacity_ids:
        return None
    observed_capacity_ids = {
        observation.get("capacity_id")
        for observation in observations
        if isinstance(observation.get("capacity_id"), str)
    }
    missing = [
        capacity_id
        for capacity_id in cited_capacity_ids
        if capacity_id not in observed_capacity_ids
    ]
    if not missing:
        return None
    return _invalid_direct_answer_observation(
        reason="direct_answer cited capacity observations that are not available",
        decision={"answer_basis": basis, "missing_capacity_ids": missing},
    )


def _capacity_observations(
    observations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        observation
        for observation in observations
        if observation.get("kind") == "capacity_observation"
        and isinstance(observation.get("capacity_id"), str)
    ]


def _invalid_direct_answer_observation(
    *,
    reason: str,
    decision: dict[str, Any],
) -> dict[str, Any]:
    return {
        "kind": "invalid_direct_answer",
        "status": "rejected",
        "reason": reason,
        "answer_excerpt": _clip_answer(decision.get("answer")),
        "answer_basis": _safe_basis(decision.get("answer_basis")),
        "instruction": (
            "direct_answer 是最终用户可见回答。没有 capacity_observation 前，"
            "只有普通闲聊或不需要任何 capability 的问题才能用 direct_answer，"
            "并且必须带 answer_basis.kind=no_capability_needed；否则返回 "
            "call_capability 或 call_capabilities。"
        ),
    }


def _basis_kind(basis: Any) -> str:
    if not isinstance(basis, dict):
        return ""
    kind = basis.get("kind")
    return kind if isinstance(kind, str) else ""


def _basis_capacity_ids(basis: Any) -> list[str]:
    if not isinstance(basis, dict):
        return []
    capacity_ids = basis.get("capacity_ids")
    if not isinstance(capacity_ids, list):
        return []
    return [item for item in capacity_ids if isinstance(item, str) and item]


def _safe_basis(basis: Any) -> dict[str, Any]:
    if not isinstance(basis, dict):
        return {}
    return {
        key: value
        for key, value in basis.items()
        if key in {"kind", "reason", "capacity_ids"}
        and isinstance(value, (str, list))
    }


def _clip_answer(answer: Any) -> str:
    if not isinstance(answer, str):
        return ""
    text = " ".join(answer.strip().split())
    if len(text) <= 240:
        return text
    return text[:239] + "..."
