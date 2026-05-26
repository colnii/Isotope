"""Research-specific deterministic capability runners."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ..features.research.flow import ResearchFlow
from ..features.research.providers import build_research_provider
from ..platform.schemas.input_contract import missing_required_input_keys


RESEARCH_SEARCH_CAPABILITY = "research.search"
VALID_RESEARCH_CAPABILITY_PROVIDERS = frozenset({"fake"})


def is_research_capability(capability_id: str) -> bool:
    return capability_id == RESEARCH_SEARCH_CAPABILITY


def validate_research_inputs(
    *,
    capability_id: str,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    if capability_id != RESEARCH_SEARCH_CAPABILITY:
        return dict(inputs or {})
    return _validate_research_search_inputs(
        inputs=inputs,
        missing_inputs=missing_inputs,
    )


def run_research_search(*, inputs: Mapping[str, Any] | None) -> dict[str, Any]:
    required_inputs = ["root", "query"]
    missing_inputs = _missing_inputs(required_inputs, inputs)
    if missing_inputs:
        raise ValueError(
            "missing required capability inputs: " + ", ".join(missing_inputs)
        )
    input_mapping = _validate_research_search_inputs(
        inputs=inputs,
        missing_inputs=missing_inputs,
    )
    provider_id = input_mapping["provider"]
    payload = ResearchFlow.in_process(
        Path(input_mapping["root"]).expanduser(),
        provider=build_research_provider(provider_id),
    ).search(input_mapping["query"]).to_dict()
    research = payload.get("research") if isinstance(payload, Mapping) else None
    sources = research.get("sources") if isinstance(research, Mapping) else None
    artifacts = payload.get("artifacts")
    artifact_refs = payload.get("artifact_refs")
    research_search: dict[str, Any] = {
        "status": payload.get("status"),
        "query": payload.get("query"),
        "provider": (
            research.get("provider") if isinstance(research, Mapping) else provider_id
        ),
        "evidence_status": (
            research.get("evidence_status") if isinstance(research, Mapping) else None
        ),
        "source_count": len(sources) if isinstance(sources, list) else 0,
        "artifact_count": len(artifacts) if isinstance(artifacts, list) else 0,
        "artifact_refs": artifact_refs if isinstance(artifact_refs, list) else [],
        "artifacts": artifacts if isinstance(artifacts, list) else [],
    }
    error = payload.get("error")
    if isinstance(error, Mapping):
        research_search["error"] = {
            "code": error.get("code"),
            "message": error.get("message"),
            "retryable": error.get("retryable"),
        }
    return {
        "kind": "capability_run_result",
        "capability_id": RESEARCH_SEARCH_CAPABILITY,
        "status": "completed",
        "runner_kind": "deterministic_local",
        "research_search": research_search,
    }


def _missing_inputs(
    required_inputs: list[str], inputs: Mapping[str, Any] | None
) -> list[str]:
    return missing_required_input_keys(inputs, required_inputs)


def _validate_research_search_inputs(
    *,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    input_mapping = inputs or {}
    for name in ("root", "query"):
        if name in missing_inputs:
            continue
        value = input_mapping.get(name)
        if not isinstance(value, str):
            raise ValueError(f"{name} must be a string")
        if not value.strip():
            raise ValueError(f"{name} must be a non-empty string")

    provider = input_mapping.get("provider", "fake")
    if not isinstance(provider, str) or not provider.strip():
        raise ValueError("provider must be a non-empty string")
    provider = provider.strip()
    if provider not in VALID_RESEARCH_CAPABILITY_PROVIDERS:
        raise ValueError("provider must be fake")

    normalized = dict(input_mapping)
    normalized["provider"] = provider
    return normalized
