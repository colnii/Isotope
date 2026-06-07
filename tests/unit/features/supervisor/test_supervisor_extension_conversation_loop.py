from __future__ import annotations

import json
from typing import Any

from isotope.features.supervisor.conversation_loop import (
    run_supervisor_conversation_events,
)
from isotope.llm.provider import LLMResponse


class RecordingConversationProvider:
    provider = "deterministic_test"
    model = "stub-conversation"

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 512,
    ) -> LLMResponse:
        self.calls.append({"messages": messages, "max_tokens": max_tokens})
        return LLMResponse(
            provider=self.provider,
            model=self.model,
            content=self.responses.pop(0),
            finish_reason="stop",
            usage={"prompt_tokens": 1, "completion_tokens": 1},
            raw={},
        )


def test_conversation_loop_loads_project_local_skills_without_model_roots(
    tmp_path,
) -> None:
    _write_test_skill(
        tmp_path / ".isotope" / "skills",
        "llm2docx",
        description="Use for Word report automation.",
        body="## Checklist\n- Inspect the Word document before editing.\n",
    )
    provider = RecordingConversationProvider(
        [
            json.dumps(
                {
                    "kind": "call_capability",
                    "capacity_id": "skills.search",
                    "arguments": {"query": "docx", "limit": 5},
                    "rationale": "Find a relevant local skill.",
                }
            ),
            json.dumps(
                {
                    "kind": "direct_answer",
                    "answer": "已找到项目 skill。",
                }
            ),
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path / "state",
            cwd=tmp_path,
            user_message="处理 Word 文档。",
            provider=provider,
            max_turns=3,
        )
    )

    assert events[1].payload["capacity_id"] == "skills.search"
    rendered_events = json.dumps(
        [event.payload for event in events],
        ensure_ascii=False,
    )
    assert str(tmp_path) not in rendered_events
    second_prompt = json.dumps(provider.calls[1]["messages"], ensure_ascii=False)
    assert "skill_search_result" in second_prompt
    assert "llm2docx" in second_prompt
    assert "## Checklist" not in second_prompt


def test_conversation_loop_loads_project_local_mcp_config_without_env(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("ISOTOPE_MCP_SERVERS_JSON", raising=False)
    monkeypatch.delenv("ISOTOPE_MCP_SERVERS_JSON_FILE", raising=False)
    config_dir = tmp_path / ".isotope"
    config_dir.mkdir()
    (config_dir / "mcp_servers.json").write_text(
        json.dumps(
            {
                "servers": {
                    "docs": {
                        "command": "node",
                        "args": ["docs-server.js"],
                        "allowed_tools": ["fetch_doc"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    provider = RecordingConversationProvider(
        [
            json.dumps(
                {
                    "kind": "call_capability",
                    "capacity_id": "mcp.servers.list",
                    "arguments": {},
                    "rationale": "List configured MCP servers.",
                }
            ),
            json.dumps(
                {
                    "kind": "direct_answer",
                    "answer": "已找到项目 MCP server。",
                }
            ),
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path / "state",
            cwd=tmp_path,
            user_message="列一下项目 MCP。",
            provider=provider,
            max_turns=3,
        )
    )

    assert events[1].payload["capacity_id"] == "mcp.servers.list"
    rendered_events = json.dumps(
        [event.payload for event in events],
        ensure_ascii=False,
    )
    assert str(tmp_path) not in rendered_events
    second_prompt = json.dumps(provider.calls[1]["messages"], ensure_ascii=False)
    assert "mcp_server_list" in second_prompt
    assert "docs" in second_prompt
    assert "node docs-server.js" in second_prompt


def _write_test_skill(
    root,
    name: str,
    *,
    description: str,
    body: str,
) -> None:
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                f"name: {name}",
                f"description: {description}",
                "---",
                body,
            ]
        ),
        encoding="utf-8",
    )
