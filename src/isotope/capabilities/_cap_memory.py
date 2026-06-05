from __future__ import annotations
from typing import Any
from ._cap_common import builtin_capability


def memory_capability_definitions(capability_type: type[Any]) -> list[Any]:
    return [
        capability_type(
        capability_id="memory.query",
        title="Memory Query",
        description=(
        "Query local memory through the existing summary / refs / "
        "provenance boundary."
        ),
        maturity="v0.2",
        shelf="product_candidate",
        domain_tags=("memory", "query", "recall", "provenance"),
        input_contract={
        "type": "object",
        "required": ["root", "query", "run_id"],
        "properties": {
        "root": {
        "type": "string",
        "x-system-input": True,
        "description": "Runtime root containing memory/*.json.",
        },
        "query": {
        "type": "string",
        "description": "Public memory search query.",
        },
        "run_id": {
        "type": "string",
        "description": "Run id for caller audit and provenance filtering.",
        },
        "scope": {
        "type": "string",
        "enum": ["thread", "run", "session"],
        "description": "Optional memory scope filter.",
        },
        "limit": {
        "type": "integer",
        "description": "Maximum records to preview.",
        "default": 20,
        },
        "controlled_expand": {
        "type": "boolean",
        "description": (
        "Materialize matched memory record content within "
        "expand_budget."
        ),
        "default": False,
        },
        "expand_budget": {
        "type": "integer",
        "description": (
        "Positive materialization budget when "
        "controlled_expand is true."
        ),
        },
        },
        },
        output_contract={
        "type": "object",
        "fields": [
        "status",
        "content_policy",
        "results",
        "controlled_expand",
        ],
        },
        safety_boundaries=(
        "memory_query_grant_gated",
        "caller_context_audited",
        "memory_record_refs_expandable",
        "controlled_expand_materialized_budgeted",
        "no_source_artifact_full_content_read",
        ),
        default_enabled=True,
        network_required=False,
        ),
        capability_type(
        capability_id="memory.recall",
        title="Memory Recall",
        description=(
        "Search local state-root memory previews without requiring "
        "the model to know an internal agent-loop run id."
        ),
        maturity="v0.2",
        shelf="product_candidate",
        domain_tags=("memory", "recall", "query", "preview", "provenance"),
        input_contract={
        "type": "object",
        "required": ["root", "query"],
        "properties": {
        "root": {
        "type": "string",
        "x-system-input": True,
        "description": "Runtime root containing memory/*.json.",
        },
        "query": {
        "type": "string",
        "description": "Public memory search query.",
        },
        "scope": {
        "type": "string",
        "enum": ["thread", "run", "session"],
        "description": "Optional memory scope filter.",
        },
        "run_id": {
        "type": "string",
        "description": (
        "Optional provenance run id filter when the "
        "user names a run."
        ),
        },
        "session_id": {
        "type": "string",
        "description": (
        "Optional provenance session id filter when "
        "the user names a session."
        ),
        },
        "limit": {
        "type": "integer",
        "description": "Maximum records to preview.",
        "default": 20,
        },
        },
        },
        output_contract={
        "type": "object",
        "fields": [
        "status",
        "content_policy",
        "summary",
        "results",
        ],
        },
        safety_boundaries=(
        "memory_public_metadata",
        "source_refs_metadata",
        "no_memory_record_content",
        "no_source_artifact_full_content_read",
        ),
        default_enabled=True,
        network_required=False,
        ),
        capability_type(
        capability_id="memory.promotion.preview",
        title="Memory Promotion Handoff",
        description=(
        "Build a public write_memory action handoff from "
        "structured artifact or external observation metadata."
        ),
        maturity="v0.2",
        shelf="product_candidate",
        domain_tags=("memory", "promotion", "write-memory", "handoff"),
        input_contract={
        "type": "object",
        "required": [
        "run_id",
        "agent_id",
        "thread_id",
        "candidate",
        ],
        "properties": {
        "run_id": {
        "type": "string",
        "description": "Run id for the proposed write_memory action.",
        },
        "agent_id": {
        "type": "string",
        "description": "Agent id proposing memory promotion.",
        },
        "thread_id": {
        "type": "string",
        "description": "Thread id for the proposed action.",
        },
        "candidate": {
        "type": "object",
        "description": (
        "Structured artifact or accepted external "
        "observation promotion candidate."
        ),
        },
        "scope": {
        "type": "string",
        "enum": ["thread", "run", "session"],
        "description": "Memory scope for the proposal.",
        "default": "run",
        },
        "quality": {
        "type": "string",
        "description": "Candidate quality label.",
        "default": "candidate",
        },
        },
        },
        output_contract={
        "type": "object",
        "fields": [
        "action_type",
        "scope",
        "summary",
        "source_refs",
        "provenance",
        "quality",
        ],
        },
        safety_boundaries=(
        "write_memory_action_payload",
        "write_memory_action_handoff",
        "canonical_event_append_via_memory_action",
        "structured_source_required",
        "source_ref_metadata_projection",
        "memory_promotion_projection",
        "memory_record_refs_expandable",
        ),
        default_enabled=True,
        network_required=False,
        ),
    ]
