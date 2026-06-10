from __future__ import annotations

import json
from typing import Any

from isotope.features.supervisor import conversation_loop
from isotope.features.supervisor.conversation_loop import run_supervisor_conversation_events
from isotope.llm.provider import LLMResponse


class RecordingProvider:
    provider = "deterministic_test"
    model = "file-read-conversation"

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def generate(self, messages: list[dict[str, str]], *, max_tokens: int = 512) -> LLMResponse:
        self.calls.append({"messages": messages, "max_tokens": max_tokens})
        return LLMResponse(
            provider=self.provider,
            model=self.model,
            content=json.dumps(self.responses.pop(0), ensure_ascii=False),
            finish_reason="stop",
            usage={},
            raw={},
        )


def test_desktop_manifest_prefers_file_read_over_legacy_code_read(tmp_path) -> None:
    provider = RecordingProvider(
        [
            {
                "kind": "direct_answer",
                "answer_basis": {"kind": "no_capability_needed", "reason": "inspect manifest"},
                "answer": "ok",
            }
        ]
    )

    list(
        run_supervisor_conversation_events(
            state_root=tmp_path / "state",
            cwd=tmp_path,
            user_message="hello",
            provider=provider,
            max_turns=1,
        )
    )

    prompt = provider.calls[0]["messages"][0]["content"]
    assert '"capability_id": "file.read"' in prompt
    assert '"capability_id": "code.read"' not in prompt


def test_file_read_observation_is_available_for_final_answer(tmp_path, monkeypatch) -> None:
    target = tmp_path / "note.md"
    target.write_text("hello from local note", encoding="utf-8")

    def fake_execute_capacity_step(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["capability_id"] == "file.read"
        return {
            "tick_result": {
                "planner_result": {
                    "step_result": {
                        "action_result": {
                            "capability_run": {
                                "kind": "capability_run_result",
                                "capability_id": "file.read",
                                "status": "completed",
                                "read": {
                                    "scope": "workspace",
                                    "status": "readable",
                                    "path": "note.md",
                                    "excerpt": "hello from local note",
                                    "truncated": False,
                                    "content_policy": "limited_excerpts_only",
                                },
                            }
                        }
                    }
                }
            }
        }

    monkeypatch.setattr(
        conversation_loop,
        "_execute_capacity_step_with_timeout",
        fake_execute_capacity_step,
    )
    provider = RecordingProvider(
        [
            {
                "kind": "call_capability",
                "capacity_id": "file.read",
                "arguments": {"scope": "workspace", "path": "note.md"},
                "rationale": "需要读取 workspace 文件。",
            },
            {
                "kind": "direct_answer",
                "answer_basis": {"kind": "observation", "capacity_ids": ["file.read"]},
                "answer": "文件内容包含 hello from local note。",
            },
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path / "state",
            cwd=tmp_path,
            user_message="读 note.md",
            provider=provider,
            max_turns=3,
        )
    )

    assert [event.event for event in events] == ["capacity_start", "capacity_result", "delta"]
    second_prompt = json.dumps(provider.calls[1]["messages"], ensure_ascii=False)
    assert "file_read" in second_prompt
    assert "hello from local note" in second_prompt
    assert events[-1].payload["text"] == "文件内容包含 hello from local note。"
