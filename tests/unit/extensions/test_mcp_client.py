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
                "source_kind": "explicit",
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
            source_kind="explicit",
        )
    ]


def test_load_mcp_server_configs_from_project_isotope_extensions(
    monkeypatch,
    tmp_path,
) -> None:
    project = tmp_path / "project"
    config_dir = project / "isotope.extensions" / "mcp"
    config_dir.mkdir(parents=True)
    (config_dir / "servers.json").write_text(
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
    monkeypatch.delenv("ISOTOPE_MCP_SERVERS_JSON_FILE", raising=False)
    monkeypatch.delenv("ISOTOPE_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.chdir(project)

    configs = load_mcp_server_configs()

    assert configs == [
        McpServerConfig(
            server_id="echo",
            command=sys.executable,
            args=(str(FIXTURE_SERVER),),
            allowed_tools=("echo",),
            source_kind="project",
        )
    ]


def test_mcp_servers_d_fragments_override_base_in_sorted_order(
    monkeypatch,
    tmp_path,
) -> None:
    project = tmp_path / "project"
    config_dir = project / "isotope.extensions" / "mcp"
    fragments = config_dir / "servers.d"
    fragments.mkdir(parents=True)
    (config_dir / "servers.json").write_text(
        json.dumps(
            {
                "servers": {
                    "echo": {"command": "base", "allowed_tools": ["echo"]}
                }
            }
        ),
        encoding="utf-8",
    )
    (fragments / "10-first.json").write_text(
        json.dumps(
            {
                "servers": {
                    "echo": {"command": "first", "allowed_tools": ["echo"]}
                }
            }
        ),
        encoding="utf-8",
    )
    (fragments / "20-second.json").write_text(
        json.dumps(
            {
                "servers": {
                    "echo": {"command": "second", "allowed_tools": ["echo"]}
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("ISOTOPE_MCP_SERVERS_JSON", raising=False)
    monkeypatch.delenv("ISOTOPE_MCP_SERVERS_JSON_FILE", raising=False)
    monkeypatch.delenv("ISOTOPE_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.chdir(project)

    configs = load_mcp_server_configs()

    assert configs[0].command == "second"
    assert configs[0].source_kind == "project"


def test_project_mcp_config_overrides_user_and_builtin(
    monkeypatch,
    tmp_path,
) -> None:
    home = tmp_path / "home"
    isotope_home = tmp_path / "isotope-home"
    project = tmp_path / "project"
    isotope_home.mkdir()
    (isotope_home / "mcp_servers.json").write_text(
        json.dumps(
            {"servers": {"echo": {"command": "user", "allowed_tools": ["echo"]}}}
        ),
        encoding="utf-8",
    )
    project_config = project / "isotope.extensions" / "mcp"
    project_config.mkdir(parents=True)
    (project_config / "servers.json").write_text(
        json.dumps(
            {
                "servers": {
                    "echo": {"command": "project", "allowed_tools": ["echo"]}
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("ISOTOPE_MCP_SERVERS_JSON", raising=False)
    monkeypatch.delenv("ISOTOPE_MCP_SERVERS_JSON_FILE", raising=False)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("ISOTOPE_HOME", str(isotope_home))
    monkeypatch.chdir(project)

    configs = load_mcp_server_configs()

    echo = next(config for config in configs if config.server_id == "echo")
    assert echo.command == "project"
    assert echo.source_kind == "project"


def test_mcp_command_ref_python_module_resolves_to_current_python(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "ISOTOPE_MCP_SERVERS_JSON",
        json.dumps(
            {
                "servers": {
                    "docs": {
                        "command_ref": "python_module:isotope.builtin_mcp.docs_server",
                        "allowed_tools": ["search_docs"],
                    }
                }
            }
        ),
    )

    configs = load_mcp_server_configs()

    assert configs == [
        McpServerConfig(
            server_id="docs",
            command=sys.executable,
            args=("-m", "isotope.builtin_mcp.docs_server"),
            allowed_tools=("search_docs",),
            source_kind="explicit",
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
            source_kind="legacy_project",
        )
    ]
