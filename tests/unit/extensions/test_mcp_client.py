from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

from isotope.extensions.mcp import (
    McpServerConfig,
    call_mcp_tool,
    list_mcp_servers,
    list_mcp_tools,
    load_mcp_server_configs,
)


FIXTURE_SERVER = (
    Path(__file__).resolve().parents[2] / "fixtures" / "mcp_echo_server.py"
)


def _server(
    *,
    enabled: bool = True,
    allowed_tools: tuple[str, ...] = ("echo", "fail"),
) -> McpServerConfig:
    return McpServerConfig(
        server_id="echo",
        command=sys.executable,
        args=(str(FIXTURE_SERVER),),
        enabled=enabled,
        allowed_tools=allowed_tools,
    )


def test_list_mcp_servers_returns_command_summary_without_raw_env() -> None:
    result = list_mcp_servers(configs=[_server()])

    assert result == {
        "kind": "mcp_server_list",
        "servers": [
            {
                "server_id": "echo",
                "transport": "stdio",
                "command_summary": f"{sys.executable} {FIXTURE_SERVER}",
                "enabled": True,
                "readiness": "ready",
                "allowed_operations": ["tools/list", "tools/call"],
            }
        ],
    }


def test_list_mcp_tools_uses_configured_stdio_server() -> None:
    result = list_mcp_tools("echo", configs=[_server()])

    assert result["kind"] == "mcp_tool_search_result"
    assert result["server_id"] == "echo"
    tool_names = [tool["tool_name"] for tool in result["tools"]]
    assert "echo" in tool_names
    echo_tool = next(tool for tool in result["tools"] if tool["tool_name"] == "echo")
    assert echo_tool["readiness"] == "ready"
    assert "input_schema" in echo_tool


def test_call_mcp_tool_returns_structured_content() -> None:
    result = call_mcp_tool(
        "echo",
        "echo",
        arguments={"text": "hello"},
        configs=[_server()],
    )

    assert result["kind"] == "mcp_tool_call_result"
    assert result["status"] == "completed"
    assert result["server_id"] == "echo"
    assert result["tool_name"] == "echo"
    assert result["is_error"] is False
    assert result["structured_content"] == {"echo": "hello"}


def test_call_mcp_tool_returns_tool_error_as_result() -> None:
    result = call_mcp_tool(
        "echo",
        "fail",
        arguments={"message": "boom"},
        configs=[_server()],
    )

    assert result["status"] == "completed"
    assert result["is_error"] is True
    assert result["error_summary"]
    assert "boom" in result["error_summary"]


def test_mcp_client_rejects_disabled_server_before_launch() -> None:
    with pytest.raises(PermissionError, match="disabled MCP server"):
        list_mcp_tools("echo", configs=[_server(enabled=False)])


def test_mcp_client_rejects_unallowed_tool_before_call() -> None:
    with pytest.raises(PermissionError, match="not allowlisted"):
        call_mcp_tool(
            "echo",
            "echo",
            arguments={"text": "hello"},
            configs=[_server(allowed_tools=())],
        )


def test_load_mcp_server_configs_from_explicit_json_mapping(monkeypatch) -> None:
    monkeypatch.setenv(
        "ISOTOPE_MCP_SERVERS_JSON",
        json.dumps(
            {
                "echo": {
                    "command": sys.executable,
                    "args": [str(FIXTURE_SERVER)],
                    "enabled": True,
                    "allowed_tools": ["echo"],
                }
            }
        ),
    )

    configs = load_mcp_server_configs()

    assert configs == [
        McpServerConfig(
            server_id="echo",
            command=sys.executable,
            args=(str(FIXTURE_SERVER),),
            enabled=True,
            allowed_tools=("echo",),
        )
    ]


def test_load_mcp_server_configs_from_json_file(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "mcp_servers.json"
    config_path.write_text(
        json.dumps(
            {
                "servers": {
                    "echo": {
                        "command": sys.executable,
                        "args": [str(FIXTURE_SERVER)],
                        "allowed_tools": ["echo"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("ISOTOPE_MCP_SERVERS_JSON", raising=False)
    monkeypatch.setenv("ISOTOPE_MCP_SERVERS_JSON_FILE", str(config_path))

    configs = load_mcp_server_configs()

    assert configs == [
        McpServerConfig(
            server_id="echo",
            command=sys.executable,
            args=(str(FIXTURE_SERVER),),
            allowed_tools=("echo",),
        )
    ]


def test_load_mcp_server_configs_from_project_local_json(
    monkeypatch,
    tmp_path,
) -> None:
    project = tmp_path / "project"
    config_dir = project / ".isotope"
    config_dir.mkdir(parents=True)
    (config_dir / "mcp_servers.json").write_text(
        json.dumps(
            {
                "servers": [
                    {
                        "server_id": "echo",
                        "command": sys.executable,
                        "args": [str(FIXTURE_SERVER)],
                        "allowed_tools": ["echo"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("ISOTOPE_MCP_SERVERS_JSON", raising=False)
    monkeypatch.delenv("ISOTOPE_MCP_SERVERS_JSON_FILE", raising=False)
    monkeypatch.delenv("ISOTOPE_HOME", raising=False)
    monkeypatch.chdir(project)

    configs = load_mcp_server_configs()

    assert configs == [
        McpServerConfig(
            server_id="echo",
            command=sys.executable,
            args=(str(FIXTURE_SERVER),),
            allowed_tools=("echo",),
        )
    ]
