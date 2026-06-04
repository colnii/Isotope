from __future__ import annotations

import json
import time
from typing import Any

from isotope.features.supervisor.conversation_loop import (
    SupervisorConversationEvent,
    run_supervisor_conversation_events,
)
from isotope.llm.provider import LLMResponse


class RecordingConversationProvider:
    provider = "fake"
    model = "fake-conversation"

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
        content = self.responses.pop(0)
        return LLMResponse(
            provider=self.provider,
            model=self.model,
            content=content,
            finish_reason="stop",
            usage={"prompt_tokens": 1, "completion_tokens": 1},
            raw={"raw_response": "must not leak"},
        )


def test_conversation_loop_accepts_plain_text_as_direct_answer(tmp_path) -> None:
    provider = RecordingConversationProvider(["你好，我在。"])

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path,
            cwd=tmp_path / "repo",
            user_message="你好",
            provider=provider,
        )
    )

    assert events == [
        SupervisorConversationEvent(
            event="delta",
            payload={"text": "你好，我在。"},
            provider="fake",
            model="fake-conversation",
        )
    ]
    assert len(provider.calls) == 1
    messages = provider.calls[0]["messages"]
    assert messages[-1] == {"role": "user", "content": "你好"}
    rendered = json.dumps(messages, ensure_ascii=False)
    assert "capacity_manifest" in rendered
    assert "direct_answer" in rendered
    assert "call_capability" in rendered
    assert "report_capability_gap" in rendered
    assert "raw_response" not in rendered


def test_conversation_loop_manifest_keeps_research_provider_policy_internal(
    tmp_path,
) -> None:
    provider = RecordingConversationProvider(["你好，我在。"])

    list(
        run_supervisor_conversation_events(
            state_root=tmp_path,
            cwd=tmp_path / "repo",
            user_message="你好",
            provider=provider,
        )
    )

    system_prompt = provider.calls[0]["messages"][0]["content"]

    assert '"capability_id": "research.search"' in system_prompt
    research_manifest = system_prompt.split('"capability_id": "research.search"', 1)[1]
    research_manifest = research_manifest.split('"capability_id": "research.promote"', 1)[
        0
    ]
    assert '"query"' in research_manifest
    assert '"provider"' not in research_manifest
    assert '"provider_gate"' not in research_manifest
    assert '"allow_network"' not in research_manifest
    assert "provider=tavily" not in system_prompt


def test_conversation_loop_calls_capability_then_returns_final_answer(tmp_path) -> None:
    provider = RecordingConversationProvider(
        [
            json.dumps(
                {
                    "kind": "call_capability",
                    "capacity_id": "artifact.review",
                    "arguments": {},
                    "rationale": "需要试跑 artifact review capability。",
                }
            ),
            json.dumps(
                {
                    "kind": "direct_answer",
                    "answer": "能力已执行，低敏结果已经返回。",
                    "rationale": "基于 capability observation 回答。",
                }
            ),
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path,
            cwd=tmp_path,
            user_message="请 review artifact。",
            provider=provider,
            max_turns=3,
        )
    )

    assert [event.event for event in events] == [
        "capacity_start",
        "capacity_result",
        "delta",
    ]
    assert events[0].payload["capacity_id"] == "artifact.review"
    assert events[0].payload["status"] == "running"
    assert events[1].payload["capacity_id"] == "artifact.review"
    assert events[1].payload["status"] == "ok"
    assert events[1].payload["result_summary"]["agent_loop_tick_status"] == "executed"
    assert events[2].payload == {"text": "能力已执行，低敏结果已经返回。"}
    assert len(provider.calls) == 2
    second_prompt = json.dumps(provider.calls[1]["messages"], ensure_ascii=False)
    assert "capacity_observation" in second_prompt
    assert "raw_response" not in second_prompt


def test_conversation_loop_filters_model_supplied_inputs_to_capability_contract(
    tmp_path,
    monkeypatch,
) -> None:
    from isotope.capabilities import research as research_capability

    class RecordingCodexProvider:
        provider_name = "codex_delegated"

        def run(self, query: str) -> dict[str, Any]:
            return {
                "research_id": "research_contract_filter_unit",
                "query": query,
                "provider": "codex_delegated",
                "created_at": "2026-06-03T00:00:00Z",
                "status": "ok",
                "evidence_status": "complete",
                "sources": [],
                "report": {
                    "summary": "Filtered research input summary.",
                    "claims": [],
                    "limitations": [],
                    "next_queries": [],
                },
                "provenance": {"provider": "codex_delegated"},
            }

    monkeypatch.setattr(
        research_capability,
        "build_research_provider",
        lambda provider_id, **kwargs: RecordingCodexProvider(),
    )

    provider = RecordingConversationProvider(
        [
            json.dumps(
                {
                    "kind": "call_capability",
                    "capacity_id": "research.search",
                    "arguments": {
                        "query": "capacity research integration",
                        "provider": "tavily",
                        "provider_gate": "tavily_research",
                        "root": "/",
                        "cwd": "/tmp/model-cwd",
                        "state_root": "/tmp/model-state-root",
                    },
                    "rationale": "需要试跑 research capability。",
                }
            ),
            json.dumps(
                {
                    "kind": "direct_answer",
                    "answer": "research.search 已执行。",
                    "rationale": "基于 capability observation 回答。",
                }
            ),
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path,
            cwd=tmp_path / "repo",
            user_message="测试一下 research.search",
            provider=provider,
            max_turns=3,
        )
    )

    assert [event.event for event in events] == [
        "capacity_start",
        "capacity_result",
        "delta",
    ]
    inputs = events[0].payload["input_summary"]
    assert inputs == {
        "query": "capacity research integration",
        "root": str(tmp_path),
    }
    assert events[1].payload["capacity_id"] == "research.search"
    assert events[1].payload["status"] == "ok"
    assert events[1].payload["result_summary"]["agent_loop_research_provider"] == (
        "codex_delegated"
    )
    assert events[2].payload == {"text": "research.search 已执行。"}


def test_conversation_loop_uses_internal_research_provider_policy(
    tmp_path,
    monkeypatch,
) -> None:
    from isotope.capabilities import research as research_capability

    provider_calls: list[dict[str, Any]] = []

    class RecordingCodexProvider:
        provider_name = "codex_delegated"

        def run(self, query: str) -> dict[str, Any]:
            return {
                "research_id": "research_codex_unit",
                "query": query,
                "provider": "codex_delegated",
                "created_at": "2026-06-03T00:00:00Z",
                "status": "ok",
                "evidence_status": "complete",
                "sources": [
                    {
                        "source_id": "src_001",
                        "title": "Codex delegated source",
                        "url": "https://example.com/research",
                        "snippet": "Codex delegated research returns cited snippets.",
                        "why_used": "unit test Codex provider",
                        "retrieved_at": "2026-06-03T00:00:00Z",
                    }
                ],
                "report": {
                    "summary": "Codex delegated research summary.",
                    "claims": [
                        {
                            "text": "Codex delegated research returns cited snippets.",
                            "source_ids": ["src_001"],
                            "confidence": "medium",
                        }
                    ],
                    "limitations": [],
                    "next_queries": [],
                },
                "provenance": {"provider": "codex_delegated"},
            }

    def build_provider(provider_id: str, **kwargs: Any) -> RecordingCodexProvider:
        provider_calls.append({"provider_id": provider_id, **kwargs})
        return RecordingCodexProvider()

    monkeypatch.setattr(
        research_capability,
        "build_research_provider",
        build_provider,
    )

    provider = RecordingConversationProvider(
        [
            json.dumps(
                {
                    "kind": "call_capability",
                    "capacity_id": "research.search",
                    "arguments": {
                        "query": "https://example.com/research",
                        "provider": "codex",
                        "provider_gate": "codex_research",
                        "allow_network": True,
                    },
                    "rationale": "需要 research.search。",
                }
            ),
            json.dumps(
                {
                    "kind": "direct_answer",
                    "answer": "research.search 已执行。",
                    "rationale": "基于 capability observation 回答。",
                }
            ),
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path,
            cwd=tmp_path / "repo",
            user_message="访问网页并总结",
            provider=provider,
            max_turns=3,
        )
    )

    inputs = events[0].payload["input_summary"]
    assert inputs == {"query": "https://example.com/research", "root": str(tmp_path)}
    assert events[0].event == "capacity_start"
    assert events[1].event == "capacity_result"
    assert events[1].payload["result_summary"]["agent_loop_research_provider"] == (
        "codex_delegated"
    )
    assert provider_calls == [
        {
            "provider_id": "codex",
            "workspace_root": str(tmp_path),
        }
    ]


def test_conversation_loop_returns_capacity_error_when_execution_times_out(
    tmp_path,
    monkeypatch,
) -> None:
    from isotope.features.supervisor import conversation_loop

    def slow_capacity_step(**kwargs: Any) -> dict[str, Any]:
        time.sleep(0.2)
        return {}

    monkeypatch.setattr(
        conversation_loop,
        "_execute_agent_loop_capacity_step",
        slow_capacity_step,
    )
    provider = RecordingConversationProvider(
        [
            json.dumps(
                {
                    "kind": "call_capability",
                    "capacity_id": "research.search",
                    "arguments": {"query": "https://example.com/research"},
                    "rationale": "需要调用 research.search。",
                }
            ),
            json.dumps(
                {
                    "kind": "direct_answer",
                    "answer": "research.search 执行超时，未拿到网页内容。",
                    "rationale": "基于 capability observation 回答。",
                }
            ),
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path,
            cwd=tmp_path / "repo",
            user_message="访问网页并总结",
            provider=provider,
            max_turns=3,
            timeout_seconds=0.05,
        )
    )

    assert [event.event for event in events] == [
        "capacity_start",
        "capacity_result",
        "delta",
    ]
    assert events[1].payload["status"] == "error"
    assert events[1].payload["result_summary"] == {
        "error_type": "TimeoutError",
        "message": "capacity execution timed out",
    }
    assert events[2].payload == {
        "text": "research.search 执行超时，未拿到网页内容。"
    }


def test_conversation_loop_records_public_metadata_capability_gap(tmp_path) -> None:
    provider = RecordingConversationProvider(
        [
            json.dumps(
                {
                    "kind": "report_capability_gap",
                    "gap": {
                        "missing_capability_kind": "supervisor.discovery.worker_list",
                        "reason": "需要查询 worker 列表，但没有对应 discovery capability。",
                        "needed_context": ["worker list", "active run state"],
                    },
                    "rationale": "缺少基础 discovery 能力。",
                }
            )
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path,
            cwd=tmp_path,
            user_message="看看哪个 worker 卡住了",
            provider=provider,
        )
    )

    assert [event.event for event in events] == ["capability_gap", "delta"]
    gap = events[0].payload
    assert gap["missing_capability_kind"] == "supervisor.discovery.worker_list"
    assert gap["source_entrypoint"] == "desktop_chat"
    assert gap["status"] == "recorded"
    assert events[1].payload["text"] == "我缺少对应的基础能力，已记录 capability gap。"
    gap_files = list((tmp_path / "supervisor" / "capability-gaps").glob("*.json"))
    assert len(gap_files) == 1
    saved = json.loads(gap_files[0].read_text(encoding="utf-8"))
    assert saved["missing_capability_kind"] == "supervisor.discovery.worker_list"
    rendered = json.dumps(saved, ensure_ascii=False)
    assert "raw_response" not in rendered
    assert "messages" not in rendered
def test_conversation_loop_executes_native_coding_capacity_with_safe_observation(
    tmp_path,
) -> None:
    workspace = tmp_path / "repo"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "app.py").write_text("value = 1\n", encoding="utf-8")
    provider = RecordingConversationProvider(
        [
            json.dumps(
                {
                    "kind": "call_capability",
                    "capacity_id": "coding_task.execute",
                    "arguments": {
                        "workspace_id": "workspace_desktop_native_coding",
                        "goal": "Change value to 2.",
                        "patch": (
                            "--- a/src/app.py\n"
                            "+++ b/src/app.py\n"
                            "@@ -1 +1 @@\n"
                            "-value = 1\n"
                            "+value = 2\n"
                        ),
                        "argv": [
                            "python3",
                            "-c",
                            "from pathlib import Path; assert Path('src/app.py').read_text() == 'value = 2\\n'",
                        ],
                        "allowed_commands": ["python3"],
                        "include_paths": ["src"],
                    },
                    "rationale": "Use native coding capacity.",
                }
            ),
            json.dumps(
                {
                    "kind": "direct_answer",
                    "answer": "已完成 native coding capacity。",
                }
            ),
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path / "state",
            cwd=workspace,
            user_message="把 src/app.py 的 value 改成 2。",
            provider=provider,
            max_turns=3,
        )
    )

    assert [event.event for event in events] == [
        "capacity_start",
        "capacity_result",
        "delta",
    ]
    assert events[0].payload["capacity_id"] == "coding_task.execute"
    assert events[1].payload["status"] == "ok"
    assert events[1].payload["result_summary"]["agent_loop_tick_status"] == "executed"
    assert events[2].payload["text"] == "已完成 native coding capacity。"
    assert (workspace / "src" / "app.py").read_text(encoding="utf-8") == "value = 1\n"
    materialized = (
        tmp_path
        / "state"
        / "workspaces"
        / "workspace_desktop_native_coding"
        / "src"
        / "app.py"
    )
    assert materialized.read_text(encoding="utf-8") == "value = 2\n"
    rendered_events = json.dumps(
        [event.payload for event in events],
        ensure_ascii=False,
    )
    assert "value = 1" not in rendered_events
    assert "value = 2" not in rendered_events
    second_prompt = json.dumps(provider.calls[1]["messages"], ensure_ascii=False)
    assert "capacity_observation" in second_prompt
    assert "value = 1" not in second_prompt
    assert "value = 2" not in second_prompt


def test_conversation_loop_executes_screen_observe_capacity_with_generic_events(
    tmp_path,
    monkeypatch,
) -> None:
    from isotope.capabilities import screen as screen_capability

    class FakeScreenBackend:
        def run(self, request):
            return {
                "backend_session_id": "fake_screen_001",
                "status": "captured",
                "started_at": "2026-05-24T00:00:00Z",
                "finished_at": "2026-05-24T00:00:01Z",
                "summary": "screen observe captured",
                "output_artifacts": [
                    {
                        "artifact_type": "screen_metadata",
                        "summary": "screen metadata captured",
                        "content": json.dumps(
                            {
                                "matched_count": 1,
                                "selected_window_id": "window_001",
                                "selection_reason": "first_match",
                                "target": {
                                    "window_id": "window_001",
                                    "title": "Notes",
                                    "app": "notepad.exe",
                                    "is_minimized": False,
                                },
                            },
                            sort_keys=True,
                        ),
                    },
                    {
                        "artifact_type": "screen_screenshot",
                        "summary": "screen screenshot captured",
                        "content": json.dumps(
                            {
                                "encoding": "base64",
                                "media_type": "image/png",
                                "width": 64,
                                "height": 32,
                                "data": "ZmFrZS1pbWFnZS1ieXRlcw==",
                            },
                            sort_keys=True,
                        ),
                    },
                ],
                "reason_code": "screen_observe_captured",
                "retryable": False,
                "resource_usage": {"window_count": 1},
            }

    monkeypatch.setattr(
        screen_capability,
        "WindowsScreenBackend",
        FakeScreenBackend,
        raising=False,
    )
    provider = RecordingConversationProvider(
        [
            json.dumps(
                {
                    "kind": "call_capability",
                    "capacity_id": "screen.observe",
                    "arguments": {
                        "target_selector": {
                            "kind": "window",
                            "selector": {"app": "notepad.exe"},
                        },
                        "target_allowlist": {"allowed_apps": ["notepad.exe"]},
                    },
                    "rationale": "Observe the allowed target window.",
                }
            ),
            json.dumps(
                {
                    "kind": "direct_answer",
                    "answer": "已完成屏幕观察。",
                }
            ),
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path / "state",
            cwd=tmp_path,
            user_message="看看记事本窗口。",
            provider=provider,
            max_turns=3,
        )
    )

    assert [event.event for event in events] == [
        "capacity_start",
        "capacity_result",
        "delta",
    ]
    assert events[0].payload["capacity_id"] == "screen.observe"
    assert events[1].payload["status"] == "ok"
    assert events[1].payload["result_summary"]["agent_loop_tick_status"] == "executed"
    assert events[1].payload["result_summary"]["agent_loop_screen_report_status"] == "ok"
    assert events[1].payload["result_summary"]["agent_loop_screen_observe_status"] == "captured"
    assert events[1].payload["result_summary"][
        "agent_loop_screen_screenshot_available"
    ] is True
    screen_artifact_details = [
        detail
        for detail in events[1].payload["details"]
        if detail["label"] == "Screen artifacts"
    ]
    assert screen_artifact_details
    assert screen_artifact_details[0]["content"]["artifacts"][1]["artifact_type"] == (
        "screen_screenshot"
    )
    assert screen_artifact_details[0]["content"]["artifacts"][1]["ref"]["artifact_id"].startswith(
        "artifact_"
    )
    assert events[2].payload["text"] == "已完成屏幕观察。"
    rendered_events = json.dumps(
        [event.payload for event in events],
        ensure_ascii=False,
    )
    assert "raw screenshot bytes" not in rendered_events
    second_messages = provider.calls[1]["messages"]
    second_prompt = json.dumps(second_messages, ensure_ascii=False)
    assert "capacity_observation" in second_prompt
    image_urls = _message_image_urls(second_messages)
    assert image_urls == ["data:image/png;base64,ZmFrZS1pbWFnZS1ieXRlcw=="]
    assert "ZmFrZS1pbWFnZS1ieXRlcw==" not in rendered_events


def _message_image_urls(messages: list[dict[str, Any]]) -> list[str]:
    urls: list[str] = []
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "image_url":
                continue
            image_url = block.get("image_url")
            if isinstance(image_url, dict) and isinstance(image_url.get("url"), str):
                urls.append(image_url["url"])
    return urls
