from __future__ import annotations

import json
from typing import Any

from isotope.features.supervisor.conversation_observations import (
    capacity_observation_message_content,
    model_observation_from_agent_loop,
)


def test_mcp_server_observation_keeps_command_summary_without_env(tmp_path) -> None:
    observation = model_observation_from_agent_loop(
        capacity_id="mcp.servers.list",
        status="ok",
        result={},
        agent_loop=_agent_loop(
            {
                "kind": "mcp_server_list",
                "status": "completed",
                "runner_kind": "extension_mcp_client",
                "servers": [
                    {
                        "server_id": "docs",
                        "transport": "stdio",
                        "command_summary": "node docs-server.js",
                        "enabled": True,
                        "readiness": "ready",
                        "allowed_operations": ["tools/list", "tools/call"],
                        "env": {"TOKEN": "secret-token"},
                    }
                ],
            }
        ),
        state_root=tmp_path,
    )

    rendered = _render_observation(observation)
    assert observation["result"]["kind"] == "mcp_server_list"
    assert observation["result"]["servers"][0]["server_id"] == "docs"
    assert observation["result"]["servers"][0]["command_summary"] == (
        "node docs-server.js"
    )
    assert "TOKEN" not in rendered
    assert "secret-token" not in rendered


def test_mcp_tool_search_observation_includes_tool_contract(tmp_path) -> None:
    observation = model_observation_from_agent_loop(
        capacity_id="mcp.tools.search",
        status="ok",
        result={},
        agent_loop=_agent_loop(
            {
                "kind": "mcp_tool_search_result",
                "status": "completed",
                "runner_kind": "extension_mcp_client",
                "server_id": "docs",
                "query": "fetch",
                "tools": [
                    {
                        "server_id": "docs",
                        "tool_name": "fetch_doc",
                        "title": "Fetch Doc",
                        "description": "Fetch one document.",
                        "input_schema": {
                            "type": "object",
                            "properties": {"url": {"type": "string"}},
                        },
                        "readiness": "ready",
                    }
                ],
            }
        ),
        state_root=tmp_path,
    )

    assert observation["result"]["kind"] == "mcp_tool_search_result"
    assert observation["result"]["server_id"] == "docs"
    assert observation["result"]["tools"][0]["tool_name"] == "fetch_doc"
    assert observation["result"]["tools"][0]["input_schema"]["properties"]["url"][
        "type"
    ] == "string"


def test_mcp_tool_call_observation_includes_result_without_arguments(tmp_path) -> None:
    observation = model_observation_from_agent_loop(
        capacity_id="mcp.tool.call",
        status="ok",
        result={},
        agent_loop=_agent_loop(
            {
                "kind": "mcp_tool_call_result",
                "status": "completed",
                "runner_kind": "extension_mcp_client",
                "server_id": "docs",
                "tool_name": "fetch_doc",
                "arguments": {"token": "secret-token"},
                "structured_content": {"title": "Fetched"},
                "content_summary": ["x" * 2100],
                "is_error": False,
                "error_summary": "",
            }
        ),
        state_root=tmp_path,
    )

    rendered = _render_observation(observation)
    assert observation["result"]["kind"] == "mcp_tool_call_result"
    assert observation["result"]["structured_content"] == {"title": "Fetched"}
    assert len(observation["result"]["content_summary"][0]) == 2002
    assert observation["result"]["content_summary"][0].endswith("...")
    assert "secret-token" not in rendered
    assert "arguments" not in rendered


def _agent_loop(capability_run: dict[str, Any]) -> dict[str, Any]:
    return {
        "tick_result": {
            "planner_result": {
                "step_result": {
                    "action_result": {
                        "capability_run": capability_run,
                    }
                }
            }
        }
    }


def _render_observation(observation: dict[str, Any]) -> str:
    return json.dumps(
        capacity_observation_message_content([observation]),
        ensure_ascii=False,
    )
