"""Research-specific deterministic capability runners."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ..features.research.flow import ResearchFlow
from ..features.research.providers import build_research_provider
from ..features.research.runner import build_research_memory_promotion_payload
from ..platform.schemas.input_contract import missing_required_input_keys


RESEARCH_PROMOTE_CAPABILITY = "research.promote"
RESEARCH_SEARCH_CAPABILITY = "research.search"
RESEARCH_CAPABILITIES = frozenset(
    {
        RESEARCH_PROMOTE_CAPABILITY,
        RESEARCH_SEARCH_CAPABILITY,
    }
)
VALID_RESEARCH_CAPABILITY_PROVIDERS = frozenset({"codex", "tavily"})
DEFAULT_RESEARCH_CAPABILITY_PROVIDER = "codex"
VALID_RESEARCH_PROMOTION_SCOPES = frozenset({"thread", "run", "session"})


def is_research_capability(capability_id: str) -> bool:
    return capability_id in RESEARCH_CAPABILITIES


def validate_research_inputs(
    *,
    capability_id: str,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    if capability_id == RESEARCH_SEARCH_CAPABILITY:
        return _validate_research_search_inputs(
            inputs=inputs,
            missing_inputs=missing_inputs,
        )
    if capability_id == RESEARCH_PROMOTE_CAPABILITY:
        return _validate_research_promote_inputs(
            inputs=inputs,
            missing_inputs=missing_inputs,
        )
    return dict(inputs or {})


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
    provider_policy = _resolve_research_provider_policy(input_mapping)
    payload = (
        ResearchFlow.in_process(
            Path(input_mapping["root"]).expanduser(),
            provider=build_research_provider(
                provider_policy["provider"],
                **_research_provider_kwargs(input_mapping, provider_policy),
            ),
        )
        .search(input_mapping["query"])
        .to_dict()
    )
    research = payload.get("research") if isinstance(payload, Mapping) else None
    sources = research.get("sources") if isinstance(research, Mapping) else None
    artifacts = payload.get("artifacts")
    artifact_refs = payload.get("artifact_refs")
    research_search: dict[str, Any] = {
        "status": payload.get("status"),
        "query": payload.get("query"),
        "provider": (
            research.get("provider")
            if isinstance(research, Mapping)
            else provider_policy["provider"]
        ),
        "evidence_status": (
            research.get("evidence_status") if isinstance(research, Mapping) else None
        ),
        "source_count": len(sources) if isinstance(sources, list) else 0,
        "artifact_count": len(artifacts) if isinstance(artifacts, list) else 0,
        "artifact_refs": artifact_refs if isinstance(artifact_refs, list) else [],
        "artifacts": artifacts if isinstance(artifacts, list) else [],
    }
    if isinstance(research, Mapping):
        research_search["report_summary"] = _research_report_summary(research)
        research_search["source_previews"] = _research_source_previews(sources)
        research_search["content_status"] = _research_content_status(research)
        research_search["content_note"] = _research_content_note(research)
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


def run_research_promote(*, inputs: Mapping[str, Any] | None) -> dict[str, Any]:
    required_inputs = ["root", "run_id", "artifact_id", "agent_id", "thread_id"]
    missing_inputs = _missing_inputs(required_inputs, inputs)
    if missing_inputs:
        raise ValueError(
            "missing required capability inputs: " + ", ".join(missing_inputs)
        )
    input_mapping = _validate_research_promote_inputs(
        inputs=inputs,
        missing_inputs=missing_inputs,
    )
    payload = build_research_memory_promotion_payload(
        Path(input_mapping["root"]).expanduser(),
        run_id=input_mapping["run_id"],
        artifact_id=input_mapping["artifact_id"],
        agent_id=input_mapping["agent_id"],
        thread_id=input_mapping["thread_id"],
        scope=input_mapping["scope"],
        quality=input_mapping["quality"],
        proposal_id=input_mapping.get("proposal_id"),
    )
    artifact = payload.get("artifact")
    proposal = payload.get("proposal")
    quality_gate = payload.get("quality_gate")
    if not isinstance(artifact, Mapping) or not isinstance(proposal, Mapping):
        raise ValueError("research promotion payload must include artifact and proposal")
    if not isinstance(quality_gate, Mapping):
        raise ValueError("research promotion payload must include quality_gate")
    action_payload = proposal.get("payload")
    action_payload = action_payload if isinstance(action_payload, Mapping) else {}
    return {
        "kind": "capability_run_result",
        "capability_id": RESEARCH_PROMOTE_CAPABILITY,
        "status": "completed",
        "runner_kind": "deterministic_local",
        "research_promotion": {
            "status": payload.get("status"),
            "artifact_type": artifact.get("artifact_type"),
            "artifact_ref": artifact.get("ref"),
            "proposal_id": proposal.get("proposal_id"),
            "action_type": proposal.get("action_type"),
            "scope": action_payload.get("scope"),
            "quality": action_payload.get("quality"),
            "summary": action_payload.get("summary"),
            "source_refs": action_payload.get("source_refs"),
            "requested_capabilities": proposal.get("requested_capabilities"),
            "quality_gate_status": quality_gate.get("status"),
            "quality_gate_reasons": quality_gate.get("reasons"),
            "memory_write": "write_memory_action_handoff",
        },
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

    return dict(input_mapping)


def _resolve_research_provider_policy(
    input_mapping: Mapping[str, Any],
) -> dict[str, Any]:
    provider_input = input_mapping.get("provider", DEFAULT_RESEARCH_CAPABILITY_PROVIDER)
    if not isinstance(provider_input, str) or not provider_input.strip():
        raise ValueError("provider must be a non-empty string")
    provider = provider_input.strip()
    if provider not in VALID_RESEARCH_CAPABILITY_PROVIDERS:
        raise ValueError("provider must be codex or tavily")

    allow_network = input_mapping.get("allow_network", False)
    if not isinstance(allow_network, bool):
        raise ValueError("allow_network must be a boolean")
    if allow_network and provider != "tavily":
        raise ValueError("allow_network is only supported for tavily provider")

    tavily_max_results = input_mapping.get("tavily_max_results")
    if tavily_max_results is not None and (
        not isinstance(tavily_max_results, int)
        or isinstance(tavily_max_results, bool)
        or tavily_max_results < 1
    ):
        raise ValueError("tavily_max_results must be a positive integer")

    return {
        "provider": provider,
        "allow_network": allow_network,
        "tavily_max_results": tavily_max_results,
    }


def _research_provider_kwargs(
    input_mapping: Mapping[str, Any],
    provider_policy: Mapping[str, Any],
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"workspace_root": input_mapping["root"]}
    if provider_policy["provider"] == "tavily":
        kwargs["tavily_enable_network"] = provider_policy["allow_network"]
        tavily_max_results = provider_policy.get("tavily_max_results")
        if isinstance(tavily_max_results, int) and not isinstance(
            tavily_max_results, bool
        ):
            kwargs["tavily_max_results"] = tavily_max_results
    return kwargs


def _research_report_summary(research: Mapping[str, Any]) -> str:
    report = research.get("report")
    if not isinstance(report, Mapping):
        return ""
    summary = report.get("summary")
    return _truncate_text(summary.strip(), 1000) if isinstance(summary, str) else ""


def _research_content_status(research: Mapping[str, Any]) -> str:
    provenance = research.get("provenance")
    if isinstance(provenance, Mapping):
        mode = provenance.get("content_mode")
        if isinstance(mode, str) and mode.strip():
            return mode.strip()
    return "source_preview"


def _research_content_note(research: Mapping[str, Any]) -> str:
    if _research_content_status(research) == "tavily_answer_with_cleaned_source_content":
        return (
            "Research result contains a Tavily answer plus cleaned source content "
            "previews for model-visible follow-up reasoning."
        )
    limitations = []
    report = research.get("report")
    if isinstance(report, Mapping) and isinstance(report.get("limitations"), list):
        limitations = [item for item in report["limitations"] if isinstance(item, str)]
    if any("snippet" in item.lower() for item in limitations):
        return (
            "Research result contains source-backed previews from search snippets, "
            "not full article text."
        )
    return "Research result contains source-backed previews, not full article text."


def _research_source_previews(sources: Any) -> list[dict[str, Any]]:
    if not isinstance(sources, list):
        return []
    previews: list[dict[str, Any]] = []
    for source in sources[:5]:
        if not isinstance(source, Mapping):
            continue
        preview: dict[str, Any] = {}
        for key in ("source_id", "title", "url", "snippet", "why_used"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                preview[key] = _truncate_text(value.strip(), 1000)
        rank = source.get("provider_rank")
        if isinstance(rank, int) and not isinstance(rank, bool):
            preview["provider_rank"] = rank
        if preview:
            previews.append(preview)
    return previews


def _truncate_text(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "..."


def _validate_research_promote_inputs(
    *,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    input_mapping = inputs or {}
    for name in ("root", "run_id", "artifact_id", "agent_id", "thread_id"):
        if name in missing_inputs:
            continue
        value = input_mapping.get(name)
        if not isinstance(value, str):
            raise ValueError(f"{name} must be a string")
        if not value.strip():
            raise ValueError(f"{name} must be a non-empty string")

    scope = input_mapping.get("scope", "run")
    if not isinstance(scope, str) or scope not in VALID_RESEARCH_PROMOTION_SCOPES:
        raise ValueError("scope must be thread, run, or session")

    quality = input_mapping.get("quality", "candidate")
    if not isinstance(quality, str) or not quality.strip():
        raise ValueError("quality must be a non-empty string")

    proposal_id = input_mapping.get("proposal_id")
    if proposal_id is not None and (
        not isinstance(proposal_id, str) or not proposal_id.strip()
    ):
        raise ValueError("proposal_id must be a non-empty string")

    normalized = dict(input_mapping)
    normalized["scope"] = scope
    normalized["quality"] = quality.strip()
    if isinstance(proposal_id, str):
        normalized["proposal_id"] = proposal_id.strip()
    return normalized
