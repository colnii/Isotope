from __future__ import annotations
from typing import Any
from ._cap_common import builtin_capability


def research_capability_definitions(capability_type: type[Any]) -> list[Any]:
    return [
        capability_type(
        capability_id="research.search",
        title="Research Search",
        description=(
        "Run the existing research flow through the runtime provider "
        "policy and return a public result summary."
        ),
        maturity="v0.2",
        shelf="product_candidate",
        domain_tags=(
        "research",
        "search",
        "web",
        "provenance",
        ),
        input_contract={
        "type": "object",
        "required": ["root", "query"],
        "properties": {
        "root": {
        "type": "string",
        "x-system-input": True,
        "description": "Runtime root used to persist research artifacts.",
        },
        "query": {
        "type": "string",
        "description": "Research query.",
        },
        "provider": {
        "type": "string",
        "enum": ["codex", "tavily"],
        "x-system-input": True,
        "description": "Internal research provider policy.",
        },
        "allow_network": {
        "type": "boolean",
        "x-system-input": True,
        "description": "Internal network execution gate.",
        },
        "tavily_max_results": {
        "type": "integer",
        "minimum": 1,
        "x-system-input": True,
        "description": "Internal Tavily result budget.",
        },
        },
        },
        output_contract={
        "type": "object",
        "fields": [
        "status",
        "query",
        "provider",
        "evidence_status",
        "source_count",
        "artifact_refs",
        "artifacts",
        ],
        },
        safety_boundaries=(
        "reuses_research_flow",
        "runtime_provider_policy",
        "network_access_controlled_by_provider_policy",
        "writes_research_artifacts",
        "public_result_metadata",
        "no_raw_transcript_return",
        ),
        default_enabled=True,
        network_required=False,
        ),
        capability_type(
        capability_id="research.promote",
        title="Research Promote",
        description=(
        "Build a write_memory proposal summary from an existing "
        "research.report record using the memory promotion boundary."
        ),
        maturity="v0.2",
        shelf="product_candidate",
        domain_tags=(
        "research",
        "promote",
        "memory",
        "proposal",
        "provenance",
        ),
        input_contract={
        "type": "object",
        "required": [
        "root",
        "run_id",
        "artifact_id",
        "agent_id",
        "thread_id",
        ],
        "properties": {
        "root": {
        "type": "string",
        "x-system-input": True,
        "description": "Runtime root containing research artifacts.",
        },
        "run_id": {
        "type": "string",
        "description": "Run id for the research.report artifact.",
        },
        "artifact_id": {
        "type": "string",
        "description": "Artifact id for the research.report artifact.",
        },
        "agent_id": {
        "type": "string",
        "description": "Agent id recorded on the write_memory proposal.",
        },
        "thread_id": {
        "type": "string",
        "description": "Thread id recorded on the write_memory proposal.",
        },
        "scope": {
        "type": "string",
        "enum": ["thread", "run", "session"],
        "description": "Memory promotion scope.",
        "default": "run",
        },
        "quality": {
        "type": "string",
        "description": "Memory candidate quality label.",
        "default": "candidate",
        },
        "proposal_id": {
        "type": "string",
        "description": "Optional stable proposal id.",
        },
        },
        },
        output_contract={
        "type": "object",
        "fields": [
        "status",
        "artifact_type",
        "artifact_ref",
        "proposal_id",
        "action_type",
        "scope",
        "quality",
        "summary",
        "source_refs",
        "requested_capabilities",
        "quality_gate_status",
        "quality_gate_reasons",
        "memory_write",
        ],
        },
        safety_boundaries=(
        "reuses_research_memory_promotion_action",
        "reuses_memory_promotion_boundary",
        "research_report_artifact_only",
        "write_memory_action_handoff",
        "research_promotion_projection",
        "write_memory_public_result_metadata",
        "public_result_metadata",
        ),
        default_enabled=True,
        network_required=False,
        ),
    ]
