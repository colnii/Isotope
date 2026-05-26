"""Memory promotion proposal boundary.

This module only prepares an explicit write_memory proposal from already
structured sources. It never writes memory records or reads raw artifact content.
"""

from __future__ import annotations

from typing import Any, Mapping

from isotope.platform.ids import new_id
from isotope.platform.schemas.actions import ActionProposal


VALID_PROMOTION_SCOPES = frozenset({"thread", "run", "session"})
RAW_PROMOTION_FIELDS = frozenset(
    {
        "content",
        "full_content",
        "provider_payload",
        "raw_content",
        "raw_text",
        "transcript",
    }
)
RAW_PROMOTION_FIELD_EXCEPTIONS = frozenset({"raw_artifact_ref"})


def build_memory_promotion_proposal(
    *,
    run_id: str,
    agent_id: str,
    thread_id: str,
    candidate: Mapping[str, Any],
    scope: str = "run",
    quality: str = "candidate",
    proposal_id: str | None = None,
) -> ActionProposal:
    """Build a write_memory ActionProposal from a structured promotion candidate."""
    clean_run_id = _required_string(run_id, "run_id")
    clean_agent_id = _required_string(agent_id, "agent_id")
    clean_thread_id = _required_string(thread_id, "thread_id")
    if scope not in VALID_PROMOTION_SCOPES:
        raise ValueError("memory promotion scope must be thread, run, or session")
    clean_quality = _required_string(quality, "quality")
    candidate_mapping = _candidate_mapping(candidate)
    source_type = _required_string(candidate_mapping.get("source_type"), "source_type")
    if source_type == "raw_text":
        raise ValueError("raw memory promotion requires structured source")
    _reject_raw_promotion_fields(candidate_mapping)

    if source_type == "artifact":
        payload = _artifact_promotion_payload(
            candidate_mapping,
            scope=scope,
            quality=clean_quality,
        )
    elif source_type == "external_observation":
        payload = _external_observation_promotion_payload(
            candidate_mapping,
            scope=scope,
            quality=clean_quality,
        )
    else:
        raise ValueError(
            "memory promotion source_type must be artifact or external_observation"
        )

    return ActionProposal(
        proposal_id=proposal_id or new_id("prop"),
        run_id=clean_run_id,
        agent_id=clean_agent_id,
        thread_id=clean_thread_id,
        action_type="write_memory",
        payload=payload,
        requested_capabilities={"tools": ["write_memory"]},
    )


def _artifact_promotion_payload(
    candidate: Mapping[str, Any],
    *,
    scope: str,
    quality: str,
) -> dict[str, Any]:
    artifact_ref = _resource_ref(candidate.get("artifact_ref"), "artifact_ref")
    summary = _required_string(candidate.get("summary"), "summary")
    artifact_type = _required_string(candidate.get("artifact_type"), "artifact_type")
    provenance = _mapping(candidate.get("provenance"), "provenance")
    source_execution_id = provenance.get("execution_id")
    output_provenance = {"promotion_source": "artifact"}
    if isinstance(source_execution_id, str) and source_execution_id:
        output_provenance["source_execution_id"] = source_execution_id
    return {
        "scope": scope,
        "content": {
            "kind": "memory_promotion_candidate",
            "source_type": "artifact",
            "artifact_type": artifact_type,
            "source_summary": summary,
        },
        "summary": summary,
        "source_refs": [artifact_ref],
        "provenance": output_provenance,
        "supersedes": [],
        "quality": quality,
    }


def _external_observation_promotion_payload(
    candidate: Mapping[str, Any],
    *,
    scope: str,
    quality: str,
) -> dict[str, Any]:
    source_ref = _resource_ref(candidate.get("source_ref"), "source_ref")
    summary = _required_string(candidate.get("summary"), "summary")
    snapshot_id = _required_string(candidate.get("snapshot_id"), "snapshot_id")
    observation = _mapping(candidate.get("observation"), "observation")
    observation_quality = _mapping(candidate.get("quality"), "candidate.quality")
    provenance = _mapping(candidate.get("provenance"), "provenance")
    raw_artifact_ref = _resource_ref(
        provenance.get("raw_artifact_ref"),
        "provenance.raw_artifact_ref",
    )
    basis_refs = _resource_ref_list(candidate.get("basis_refs"), "basis_refs")
    return {
        "scope": scope,
        "content": {
            "kind": "memory_promotion_candidate",
            "source_type": "external_observation",
            "snapshot_id": snapshot_id,
            "source_summary": summary,
            "observation": dict(observation),
            "quality": dict(observation_quality),
        },
        "summary": summary,
        "source_refs": [source_ref],
        "provenance": {
            "promotion_source": "external_observation",
            "snapshot_id": snapshot_id,
            "raw_artifact_ref": raw_artifact_ref,
            "basis_refs": basis_refs,
        },
        "supersedes": [],
        "quality": quality,
    }


def _candidate_mapping(candidate: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(candidate, Mapping):
        raise TypeError("memory promotion candidate must be a mapping")
    return candidate


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a mapping")
    return value


def _required_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _resource_ref(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a structured ResourceRef dict")
    ref = dict(value)
    for key in ("ref_type", "scope", "run_id", "artifact_id"):
        _required_string(ref.get(key), f"{field_name}.{key}")
    if ref["ref_type"] != "artifact":
        raise ValueError(f"{field_name} must be an artifact ResourceRef")
    return ref


def _resource_ref_list(value: Any, field_name: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field_name} must be a non-empty list")
    return [
        _resource_ref(item, f"{field_name}[{index}]")
        for index, item in enumerate(value)
    ]


def _reject_raw_promotion_fields(candidate: Mapping[str, Any]) -> None:
    _reject_raw_promotion_fields_at(candidate)


def _reject_raw_promotion_fields_at(value: Any) -> None:
    if isinstance(value, Mapping):
        for field_name, nested in value.items():
            if (
                field_name in RAW_PROMOTION_FIELDS
                and field_name not in RAW_PROMOTION_FIELD_EXCEPTIONS
            ):
                raise ValueError(f"raw memory promotion cannot include {field_name}")
            _reject_raw_promotion_fields_at(nested)
    elif isinstance(value, list):
        for nested in value:
            _reject_raw_promotion_fields_at(nested)


__all__ = [
    "VALID_PROMOTION_SCOPES",
    "build_memory_promotion_proposal",
]
