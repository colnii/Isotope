"""Explicit MCP stdio client wrapper for Isotope extension capabilities."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@dataclass(frozen=True)
class McpServerConfig:
    server_id: str
    command: str
    args: tuple[str, ...] = ()
    env: Mapping[str, str] | None = None
    enabled: bool = True
    allowed_tools: tuple[str, ...] = ()

    def command_summary(self) -> str:
        return " ".join([self.command, *self.args]).strip()


def list_mcp_servers(*, configs: Iterable[McpServerConfig]) -> dict[str, Any]:
    servers = []
    for config in configs:
        _validate_config(config)
        servers.append(
            {
                "server_id": config.server_id,
                "transport": "stdio",
                "command_summary": config.command_summary(),
                "enabled": config.enabled,
                "readiness": "ready" if config.enabled else "disabled",
                "allowed_operations": (
                    ["tools/list", "tools/call"] if config.enabled else []
                ),
            }
        )
    return {"kind": "mcp_server_list", "servers": servers}


def load_mcp_server_configs(*, cwd: Path | str | None = None) -> list[McpServerConfig]:
    raw = os.environ.get("ISOTOPE_MCP_SERVERS_JSON")
    if raw:
        return _mcp_server_configs_from_payload(
            json.loads(raw),
            source="ISOTOPE_MCP_SERVERS_JSON",
        )
    path = _mcp_server_config_path(cwd=cwd)
    if path is None:
        return []
    return _mcp_server_configs_from_payload(
        json.loads(path.read_text(encoding="utf-8")),
        source=str(path),
    )


def _mcp_server_config_path(*, cwd: Path | str | None) -> Path | None:
    explicit = os.environ.get("ISOTOPE_MCP_SERVERS_JSON_FILE")
    if explicit:
        return Path(explicit).expanduser()
    candidates: list[Path] = []
    isotope_home = os.environ.get("ISOTOPE_HOME")
    if isotope_home:
        candidates.append(Path(isotope_home).expanduser() / "mcp_servers.json")
    project_root = Path(cwd).expanduser() if cwd is not None else Path.cwd()
    candidates.append(project_root / ".isotope" / "mcp_servers.json")
    candidates.append(Path.home() / ".isotope" / "mcp_servers.json")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _mcp_server_configs_from_payload(
    payload: Any,
    *,
    source: str,
) -> list[McpServerConfig]:
    if not isinstance(payload, dict):
        raise ValueError(f"{source} must be a JSON object")
    servers = payload.get("servers")
    if isinstance(servers, (dict, list)):
        payload = servers
    if isinstance(payload, list):
        return [
            _mcp_server_config_from_mapping(item.get("server_id"), item)
            for item in payload
            if isinstance(item, dict)
        ]
    if not isinstance(payload, dict):
        raise ValueError(f"{source} servers must be an object or array")
    configs: list[McpServerConfig] = []
    for server_id, value in payload.items():
        configs.append(_mcp_server_config_from_mapping(server_id, value))
    return configs


def _mcp_server_config_from_mapping(
    server_id: Any,
    value: Any,
) -> McpServerConfig:
    if not isinstance(server_id, str) or not server_id:
        raise ValueError("MCP server id must be a non-empty string")
    if not isinstance(value, dict):
        raise ValueError("MCP server config must be an object")
    command = value.get("command")
    args = value.get("args", [])
    env = value.get("env")
    enabled = value.get("enabled", True)
    allowed_tools = value.get("allowed_tools", [])
    if not isinstance(command, str) or not command:
        raise ValueError("MCP server command must be a non-empty string")
    if not isinstance(args, list) or not all(isinstance(item, str) for item in args):
        raise ValueError("MCP server args must be an array of strings")
    if env is not None and (
        not isinstance(env, dict)
        or not all(
            isinstance(key, str) and isinstance(item, str)
            for key, item in env.items()
        )
    ):
        raise ValueError("MCP server env must be an object of strings")
    if not isinstance(enabled, bool):
        raise ValueError("MCP server enabled must be a bool")
    if not isinstance(allowed_tools, list) or not all(
        isinstance(item, str) for item in allowed_tools
    ):
        raise ValueError("MCP server allowed_tools must be an array of strings")
    return McpServerConfig(
        server_id=server_id,
        command=command,
        args=tuple(args),
        env=env,
        enabled=enabled,
        allowed_tools=tuple(allowed_tools),
    )


def list_mcp_tools(
    server_id: str,
    *,
    configs: Iterable[McpServerConfig],
    query: str = "",
) -> dict[str, Any]:
    if not isinstance(query, str):
        raise ValueError("query must be a string")
    config = _find_enabled_server(server_id, configs)
    tools = asyncio.run(_list_tools(config))
    normalized_query = query.strip().lower()
    visible = []
    for tool in tools:
        tool_name = str(tool.get("tool_name", ""))
        haystack = " ".join(
            [
                tool_name,
                str(tool.get("title", "")),
                str(tool.get("description", "")),
            ]
        ).lower()
        if normalized_query and normalized_query not in haystack:
            continue
        if tool_name not in config.allowed_tools:
            tool["readiness"] = "not_allowlisted"
        visible.append(tool)
    return {
        "kind": "mcp_tool_search_result",
        "server_id": server_id,
        "query": query,
        "tools": visible,
    }


def call_mcp_tool(
    server_id: str,
    tool_name: str,
    *,
    arguments: Mapping[str, Any] | None = None,
    configs: Iterable[McpServerConfig],
) -> dict[str, Any]:
    config = _find_enabled_server(server_id, configs)
    if not isinstance(tool_name, str) or not tool_name:
        raise ValueError("tool_name must be a non-empty string")
    if tool_name not in config.allowed_tools:
        raise PermissionError(f"MCP tool is not allowlisted: {tool_name}")
    if arguments is not None and not isinstance(arguments, Mapping):
        raise ValueError("arguments must be a mapping")
    return asyncio.run(_call_tool(config, tool_name, dict(arguments or {})))


async def _list_tools(config: McpServerConfig) -> list[dict[str, Any]]:
    async with stdio_client(_stdio_params(config)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            response = await session.list_tools()
            result = []
            for tool in response.tools:
                result.append(
                    {
                        "server_id": config.server_id,
                        "tool_name": tool.name,
                        "title": getattr(tool, "title", None) or tool.name,
                        "description": tool.description or "",
                        "input_schema": tool.inputSchema or {},
                        "readiness": "ready",
                    }
                )
            return result


async def _call_tool(
    config: McpServerConfig,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    async with stdio_client(_stdio_params(config)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            response = await session.call_tool(tool_name, arguments)
            return _tool_call_result(config.server_id, tool_name, response)


def _tool_call_result(server_id: str, tool_name: str, response: Any) -> dict[str, Any]:
    structured = getattr(response, "structuredContent", None)
    if structured is None:
        structured = getattr(response, "structured_content", None)
    is_error = bool(getattr(response, "isError", False))
    text_parts = []
    for item in getattr(response, "content", []) or []:
        text = getattr(item, "text", None)
        if isinstance(text, str) and text:
            text_parts.append(text[:2000])
    return {
        "kind": "mcp_tool_call_result",
        "status": "completed",
        "server_id": server_id,
        "tool_name": tool_name,
        "structured_content": structured,
        "content_summary": text_parts[:5],
        "is_error": is_error,
        "error_summary": "\n".join(text_parts[:2]) if is_error else "",
    }


def _stdio_params(config: McpServerConfig) -> StdioServerParameters:
    return StdioServerParameters(
        command=config.command,
        args=list(config.args),
        env=dict(config.env or {}),
    )


def _find_enabled_server(
    server_id: str,
    configs: Iterable[McpServerConfig],
) -> McpServerConfig:
    if not isinstance(server_id, str) or not server_id:
        raise ValueError("server_id must be a non-empty string")
    for config in configs:
        _validate_config(config)
        if config.server_id != server_id:
            continue
        if not config.enabled:
            raise PermissionError(f"disabled MCP server: {server_id}")
        return config
    raise ValueError(f"unknown MCP server: {server_id}")


def _validate_config(config: McpServerConfig) -> None:
    if not isinstance(config, McpServerConfig):
        raise ValueError("config must be an McpServerConfig")
    if not isinstance(config.server_id, str) or not config.server_id:
        raise ValueError("server_id must be a non-empty string")
    if not isinstance(config.command, str) or not config.command:
        raise ValueError("command must be a non-empty string")
    if not isinstance(config.args, tuple) or not all(
        isinstance(item, str) for item in config.args
    ):
        raise ValueError("args must be a tuple of strings")
    if config.env is not None and (
        not isinstance(config.env, Mapping)
        or not all(
            isinstance(key, str) and isinstance(item, str)
            for key, item in config.env.items()
        )
    ):
        raise ValueError("env must be a mapping of strings")
    if not isinstance(config.enabled, bool):
        raise ValueError("enabled must be bool")
    if not isinstance(config.allowed_tools, tuple) or not all(
        isinstance(item, str) for item in config.allowed_tools
    ):
        raise ValueError("allowed_tools must be a tuple of strings")
