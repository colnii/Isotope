"""Capability adapters for local skills and configured MCP servers."""

from __future__ import annotations

from typing import Any, Mapping

from isotope.extensions.mcp import (
    call_mcp_tool,
    list_mcp_servers,
    list_mcp_tools,
    load_mcp_server_configs,
)
from isotope.extensions.skills import describe_skill, discover_skills


SKILLS_SEARCH_CAPABILITY = "skills.search"
SKILLS_DESCRIBE_CAPABILITY = "skills.describe"
MCP_SERVERS_LIST_CAPABILITY = "mcp.servers.list"
MCP_TOOLS_SEARCH_CAPABILITY = "mcp.tools.search"
MCP_TOOL_CALL_CAPABILITY = "mcp.tool.call"
EXTENSION_CAPABILITIES = {
    SKILLS_SEARCH_CAPABILITY,
    SKILLS_DESCRIBE_CAPABILITY,
    MCP_SERVERS_LIST_CAPABILITY,
    MCP_TOOLS_SEARCH_CAPABILITY,
    MCP_TOOL_CALL_CAPABILITY,
}


def extension_capability_definitions(capability_type: type[Any]) -> list[Any]:
    return [
        capability_type(
            capability_id=SKILLS_SEARCH_CAPABILITY,
            title="Skills Search",
            description=(
                "Search local Codex skills by metadata without loading skill bodies."
            ),
            maturity="v0.2",
            shelf="product_candidate",
            domain_tags=("skills", "extensions", "discovery"),
            input_contract={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query.",
                        "default": "",
                    },
                    "roots": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional explicit skill roots.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum returned skills.",
                        "default": 20,
                    },
                },
            },
            output_contract={
                "type": "object",
                "fields": ["status", "runner_kind", "skills", "skill_count", "skipped"],
            },
            safety_boundaries=(
                "read_only_skill_metadata",
                "no_skill_body_in_manifest",
                "no_code_execution",
            ),
            default_enabled=True,
            network_required=False,
        ),
        capability_type(
            capability_id=SKILLS_DESCRIBE_CAPABILITY,
            title="Skills Describe",
            description="Load one selected Codex skill guide with bounded content.",
            maturity="v0.2",
            shelf="product_candidate",
            domain_tags=("skills", "extensions", "progressive-disclosure"),
            input_contract={
                "type": "object",
                "required": ["skill_id"],
                "properties": {
                    "skill_id": {
                        "type": "string",
                        "description": "Skill id returned by skills.search.",
                    },
                    "roots": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional explicit skill roots.",
                    },
                    "max_body_chars": {
                        "type": "integer",
                        "description": "Maximum returned skill guide characters.",
                        "default": 12000,
                    },
                },
            },
            output_contract={
                "type": "object",
                "fields": [
                    "status",
                    "runner_kind",
                    "skill",
                    "body",
                    "body_truncated",
                    "linked_paths",
                ],
            },
            safety_boundaries=(
                "read_only_selected_skill_body",
                "bounded_body",
                "no_linked_file_autoload",
                "no_code_execution",
            ),
            default_enabled=True,
            network_required=False,
        ),
        *_mcp_capability_definitions(capability_type),
    ]


def _mcp_capability_definitions(capability_type: type[Any]) -> list[Any]:
    return [
        capability_type(
            capability_id=MCP_SERVERS_LIST_CAPABILITY,
            title="MCP Servers List",
            description="List explicitly configured MCP stdio servers and readiness.",
            maturity="v0.2",
            shelf="product_candidate",
            domain_tags=("mcp", "extensions", "discovery"),
            input_contract={"type": "object"},
            output_contract={
                "type": "object",
                "fields": ["status", "runner_kind", "servers"],
            },
            safety_boundaries=(
                "configured_servers_only",
                "command_summary_only",
                "no_tool_call",
            ),
            default_enabled=True,
            network_required=False,
        ),
        capability_type(
            capability_id=MCP_TOOLS_SEARCH_CAPABILITY,
            title="MCP Tools Search",
            description=(
                "List or search tools from one explicitly configured MCP stdio server."
            ),
            maturity="v0.2",
            shelf="product_candidate",
            domain_tags=("mcp", "tools", "extensions", "discovery"),
            input_contract={
                "type": "object",
                "required": ["server_id"],
                "properties": {
                    "server_id": {
                        "type": "string",
                        "description": "Configured MCP server id.",
                    },
                    "query": {
                        "type": "string",
                        "description": "Optional tool search query.",
                        "default": "",
                    },
                },
            },
            output_contract={
                "type": "object",
                "fields": ["status", "runner_kind", "tools"],
            },
            safety_boundaries=(
                "configured_servers_only",
                "allowed_tool_metadata",
                "no_tool_call",
            ),
            default_enabled=True,
            network_required=False,
        ),
        capability_type(
            capability_id=MCP_TOOL_CALL_CAPABILITY,
            title="MCP Tool Call",
            description=(
                "Call one allowlisted tool on one explicitly configured MCP stdio server."
            ),
            maturity="v0.2",
            shelf="product_candidate",
            domain_tags=("mcp", "tools", "extensions", "execution"),
            input_contract={
                "type": "object",
                "required": ["server_id", "tool_name"],
                "properties": {
                    "server_id": {
                        "type": "string",
                        "description": "Configured MCP server id.",
                    },
                    "tool_name": {
                        "type": "string",
                        "description": "Allowlisted MCP tool name.",
                    },
                    "arguments": {
                        "type": "object",
                        "description": "JSON arguments for the MCP tool.",
                        "default": {},
                    },
                },
            },
            output_contract={
                "type": "object",
                "fields": [
                    "status",
                    "runner_kind",
                    "structured_content",
                    "content_summary",
                    "is_error",
                ],
            },
            safety_boundaries=(
                "configured_servers_only",
                "allowlisted_tools_only",
                "bounded_result_summary",
            ),
            default_enabled=True,
            network_required=False,
        ),
    ]


def is_extension_capability(capability_id: str) -> bool:
    return capability_id in EXTENSION_CAPABILITIES


def validate_extension_inputs(
    *,
    capability_id: str,
    inputs: Mapping[str, Any],
    missing_inputs: list[str],
) -> None:
    if capability_id not in EXTENSION_CAPABILITIES:
        return
    if missing_inputs:
        return
    roots = inputs.get("roots")
    if roots is not None and not isinstance(roots, list):
        raise ValueError("roots must be an array")
    arguments = inputs.get("arguments")
    if arguments is not None and not isinstance(arguments, Mapping):
        raise ValueError("arguments must be an object")


def run_extension_capability(
    capability_id: str,
    *,
    inputs: Mapping[str, Any],
) -> dict[str, Any]:
    if capability_id == SKILLS_SEARCH_CAPABILITY:
        result = discover_skills(
            roots=inputs.get("roots"),
            query=str(inputs.get("query", "")),
            limit=int(inputs.get("limit", 20)),
        )
        return {
            "status": "completed",
            "runner_kind": "extension_skill_registry",
            **result,
        }
    if capability_id == SKILLS_DESCRIBE_CAPABILITY:
        result = describe_skill(
            str(inputs["skill_id"]),
            roots=inputs.get("roots"),
            max_body_chars=int(inputs.get("max_body_chars", 12000)),
        )
        return {
            "status": "completed",
            "runner_kind": "extension_skill_registry",
            **result,
        }
    if capability_id == MCP_SERVERS_LIST_CAPABILITY:
        return {
            "status": "completed",
            "runner_kind": "extension_mcp_client",
            **list_mcp_servers(configs=load_mcp_server_configs()),
        }
    if capability_id == MCP_TOOLS_SEARCH_CAPABILITY:
        return {
            "status": "completed",
            "runner_kind": "extension_mcp_client",
            **list_mcp_tools(
                str(inputs["server_id"]),
                configs=load_mcp_server_configs(),
                query=str(inputs.get("query", "")),
            ),
        }
    if capability_id == MCP_TOOL_CALL_CAPABILITY:
        arguments = inputs.get("arguments")
        return {
            "status": "completed",
            "runner_kind": "extension_mcp_client",
            **call_mcp_tool(
                str(inputs["server_id"]),
                str(inputs["tool_name"]),
                arguments=arguments if isinstance(arguments, Mapping) else {},
                configs=load_mcp_server_configs(),
            ),
        }
    raise PermissionError(f"extension capability is not implemented: {capability_id}")
