"""Memory-specific deterministic capability runners."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ..memory import LocalMemoryQueryService
from ..memory.promotion import build_memory_promotion_proposal
from ..platform.schemas.input_contract import missing_required_input_keys
from ..platform.state.memory_store import FileMemoryStore


MEMORY_QUERY_CAPABILITY = "memory.query"
MEMORY_PROMOTION_PREVIEW_CAPABILITY = "memory.promotion.preview"
VALID_MEMORY_QUERY_SCOPES = frozenset({"thread", "run", "session"})
VALID_MEMORY_PROMOTION_SCOPES = frozenset({"thread", "run", "session"})


def is_memory_readonly_capability(capability_id: str) -> bool:
    return capability_id in {
        MEMORY_QUERY_CAPABILITY,
        MEMORY_PROMOTION_PREVIEW_CAPABILITY,
    }


def validate_memory_readonly_inputs(
    *,
    capability_id: str,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    if capability_id != MEMORY_QUERY_CAPABILITY:
        if capability_id == MEMORY_PROMOTION_PREVIEW_CAPABILITY:
            return _validate_memory_promotion_preview_inputs(
                inputs=inputs,
                missing_inputs=missing_inputs,
            )
        return dict(inputs or {})
    return _validate_memory_query_inputs(
        inputs=inputs,
        missing_inputs=missing_inputs,
    )


def run_memory_query(*, inputs: Mapping[str, Any] | None) -> dict[str, Any]:
    required_inputs = ["root", "query", "run_id"]
    missing_inputs = _missing_inputs(required_inputs, inputs)
    if missing_inputs:
        raise ValueError("missing required capability inputs: " + ", ".join(missing_inputs))
    input_mapping = _validate_memory_query_inputs(
        inputs=inputs,
        missing_inputs=missing_inputs,
    )
    root = Path(input_mapping["root"]).expanduser()
    grants: dict[str, Any] = {"memory": {"query": True}}
    controlled_expand = bool(input_mapping.get("controlled_expand", False))
    if controlled_expand:
        grants["memory"]["controlled_expand"] = True
        grants["memory"]["expand_budget"] = input_mapping["expand_budget"]

    payload = LocalMemoryQueryService(FileMemoryStore(root)).query(
        run_id=input_mapping["run_id"],
        query=input_mapping["query"],
        grants=grants,
        caller_context={
            "run_id": input_mapping["run_id"],
            "caller": "capability_runner",
            "purpose": "memory_query_capability",
        },
        controlled_expand=controlled_expand,
        scope=input_mapping.get("scope"),
        limit=input_mapping["limit"],
    )
    return {
        "kind": "capability_run_result",
        "capability_id": MEMORY_QUERY_CAPABILITY,
        "status": "completed",
        "runner_kind": "deterministic_readonly",
        "memory_query": payload,
    }


def run_memory_promotion_preview(
    *,
    inputs: Mapping[str, Any] | None,
) -> dict[str, Any]:
    required_inputs = ["run_id", "agent_id", "thread_id", "candidate"]
    missing_inputs = _missing_inputs(required_inputs, inputs)
    if missing_inputs:
        raise ValueError("missing required capability inputs: " + ", ".join(missing_inputs))
    input_mapping = _validate_memory_promotion_preview_inputs(
        inputs=inputs,
        missing_inputs=missing_inputs,
    )
    proposal = build_memory_promotion_proposal(
        run_id=input_mapping["run_id"],
        agent_id=input_mapping["agent_id"],
        thread_id=input_mapping["thread_id"],
        candidate=input_mapping["candidate"],
        scope=input_mapping["scope"],
        quality=input_mapping["quality"],
    )
    return {
        "kind": "capability_run_result",
        "capability_id": MEMORY_PROMOTION_PREVIEW_CAPABILITY,
        "status": "completed",
        "runner_kind": "deterministic_readonly",
        "memory_promotion_preview": _memory_promotion_preview(proposal),
    }


def _missing_inputs(
    required_inputs: list[str], inputs: Mapping[str, Any] | None
) -> list[str]:
    return missing_required_input_keys(inputs, required_inputs)


def _validate_memory_query_inputs(
    *,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    input_mapping = inputs or {}
    for name in ("root", "query", "run_id"):
        if name in missing_inputs:
            continue
        value = input_mapping.get(name)
        if not isinstance(value, str):
            raise ValueError(f"{name} must be a string")
        if not value.strip():
            raise ValueError(f"{name} must be a non-empty string")

    scope = input_mapping.get("scope")
    if scope is not None and scope not in VALID_MEMORY_QUERY_SCOPES:
        raise ValueError("scope must be thread, run, or session")

    limit = input_mapping.get("limit", 20)
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise ValueError("limit must be a positive integer")

    controlled_expand = input_mapping.get("controlled_expand", False)
    if not isinstance(controlled_expand, bool):
        raise ValueError("controlled_expand must be bool")

    normalized = dict(input_mapping)
    normalized["limit"] = limit
    normalized["controlled_expand"] = controlled_expand
    if controlled_expand:
        if "expand_budget" not in input_mapping:
            raise ValueError("expand_budget is required when controlled_expand is true")
        expand_budget = input_mapping["expand_budget"]
        if (
            isinstance(expand_budget, bool)
            or not isinstance(expand_budget, int)
            or expand_budget <= 0
        ):
            raise ValueError("expand_budget must be a positive integer")
        normalized["expand_budget"] = expand_budget
    elif "expand_budget" in input_mapping:
        expand_budget = input_mapping["expand_budget"]
        if (
            isinstance(expand_budget, bool)
            or not isinstance(expand_budget, int)
            or expand_budget <= 0
        ):
            raise ValueError("expand_budget must be a positive integer")
    return normalized


def _validate_memory_promotion_preview_inputs(
    *,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    input_mapping = inputs or {}
    for name in ("run_id", "agent_id", "thread_id"):
        if name in missing_inputs:
            continue
        value = input_mapping.get(name)
        if not isinstance(value, str):
            raise ValueError(f"{name} must be a string")
        if not value.strip():
            raise ValueError(f"{name} must be a non-empty string")

    if "candidate" not in missing_inputs:
        candidate = input_mapping.get("candidate")
        if not isinstance(candidate, Mapping):
            raise TypeError("candidate must be a mapping")

    scope = input_mapping.get("scope", "run")
    if scope not in VALID_MEMORY_PROMOTION_SCOPES:
        raise ValueError("scope must be thread, run, or session")
    quality = input_mapping.get("quality", "candidate")
    if not isinstance(quality, str) or not quality.strip():
        raise ValueError("quality must be a non-empty string")

    normalized = dict(input_mapping)
    normalized["scope"] = scope
    normalized["quality"] = quality
    if not missing_inputs:
        build_memory_promotion_proposal(
            run_id=normalized["run_id"],
            agent_id=normalized["agent_id"],
            thread_id=normalized["thread_id"],
            candidate=normalized["candidate"],
            scope=normalized["scope"],
            quality=normalized["quality"],
        )
    return normalized


def _memory_promotion_preview(proposal: Any) -> dict[str, Any]:
    payload = proposal.payload
    return {
        "action_type": proposal.action_type,
        "requested_capabilities": dict(proposal.requested_capabilities),
        "scope": payload["scope"],
        "quality": payload["quality"],
        "summary": payload["summary"],
        "source_refs": [dict(ref) for ref in payload["source_refs"]],
        "provenance": dict(payload["provenance"]),
        "content_policy": "memory_record_refs_expandable",
    }
