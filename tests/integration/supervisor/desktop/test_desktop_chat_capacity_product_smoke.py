from __future__ import annotations

import json
from typing import Any

from isotope.features.supervisor.desktop_chat import stream_desktop_chat_events
from isotope.features.supervisor.planner.goal_queue import record_supervisor_goal
from isotope.llm.provider import LLMResponse


class ProductSmokeProvider:
    provider = "deterministic_product_smoke"
    model = "desktop-chat-smoke"

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = [json.dumps(response, ensure_ascii=False) for response in responses]
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
            raw={"raw_response": "must not leak"},
        )


def test_desktop_chat_capacity_product_smoke_covers_core_actions(
    tmp_path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _install_research_provider_stub(monkeypatch)
    _install_self_repair_launch_stubs(monkeypatch, workspace=workspace, state_root=tmp_path)
    record_supervisor_goal(
        codex_home=tmp_path,
        goal="把 Desktop chat 打成可验收产品流",
        cwd=workspace,
        target_name="desktop-chat",
    )

    research = _run_product_flow(
        state_root=tmp_path,
        cwd=workspace,
        question="搜索 Desktop chat capacity 产品流",
        provider=ProductSmokeProvider(
            [
                {
                    "kind": "call_capability",
                    "capacity_id": "research.search",
                    "arguments": {"query": "Desktop chat capacity product smoke"},
                    "rationale": "用户要求搜索资料。",
                },
                {
                    "kind": "direct_answer",
                    "answer": "搜索已完成，结果来自 research observation。",
                },
            ]
        ),
    )
    project_status = _run_product_flow(
        state_root=tmp_path,
        cwd=workspace,
        question="现在项目状态怎样？",
        provider=ProductSmokeProvider(
            [
                {
                    "kind": "call_capability",
                    "capacity_id": "supervisor.project_status",
                    "arguments": {},
                    "rationale": "用户要求查看项目态势。",
                },
                {
                    "kind": "direct_answer",
                    "answer": "项目状态已读取。",
                },
            ]
        ),
    )
    self_repair = _run_product_flow(
        state_root=tmp_path,
        cwd=workspace,
        question="这个缺口让 Isotope 自己修一下。",
        provider=ProductSmokeProvider(
            [
                {
                    "kind": "call_capability",
                    "capacity_id": "isotope.self_repair",
                    "arguments": {
                        "user_goal": "让 Desktop chat 能完整验收 capacity 产品流。",
                        "failure_summary": "缺少产品级端到端 smoke。",
                        "suggested_fix_summary": "补 integration smoke。",
                    },
                    "rationale": "用户要求 Isotope 自修复能力缺口。",
                },
                {
                    "kind": "direct_answer",
                    "answer": "已启动 Isotope 自修复 worker。",
                },
            ]
        ),
    )

    assert research["start"]["capacity_id"] == "research.search"
    assert research["start"]["inputs"] == {
        "query": "Desktop chat capacity product smoke",
        "root": str(tmp_path),
    }
    assert research["result"]["status"] == "ok"
    assert research["result"]["result"]["agent_loop_research_provider"] == (
        "codex_delegated"
    )
    assert _detail_labels(research["result"]) == {
        "Inputs",
        "Result",
        "Research artifacts",
    }
    assert "Research product smoke summary." in research["second_prompt"]
    assert "raw_response" not in research["rendered"]
    assert "raw_output" not in research["second_prompt"]

    assert project_status["start"]["capacity_id"] == "supervisor.project_status"
    assert project_status["start"]["inputs"] == {}
    assert project_status["result"]["status"] == "ok"
    assert project_status["result"]["result"]["agent_loop_project_status_status"] == (
        "completed"
    )
    assert "project_state" in project_status["second_prompt"]
    assert "把 Desktop chat 打成可验收产品流" in project_status["second_prompt"]
    assert "raw_response" not in project_status["rendered"]

    assert self_repair["start"]["capacity_id"] == "isotope.self_repair"
    assert "state_root" not in self_repair["start"]["inputs"]
    assert "cwd" not in self_repair["start"]["inputs"]
    assert self_repair["result"]["status"] == "ok"
    assert self_repair["result"]["result"]["agent_loop_self_repair_status"] == (
        "launched"
    )
    assert self_repair["result"]["result"]["agent_loop_self_repair_managed_name"] == (
        "desktop-self-repair"
    )
    assert "desktop-self-repair" in self_repair["second_prompt"]
    assert "Isotope self-repair request" not in self_repair["second_prompt"]
    assert "raw_response" not in self_repair["rendered"]


def _run_product_flow(
    *,
    state_root,
    cwd,
    question: str,
    provider: ProductSmokeProvider,
) -> dict[str, Any]:
    events = list(
        stream_desktop_chat_events(
            state_root=state_root,
            cwd=cwd,
            question=question,
            provider=provider,
        )
    )

    assert [event.event for event in events[:3]] == [
        "capacity_start",
        "capacity_update",
        "capacity_result",
    ]
    answer = "".join(
        event.payload["text"] for event in events if event.event == "delta"
    )
    assert answer
    return {
        "start": events[0].payload,
        "result": events[2].payload,
        "answer": answer,
        "second_prompt": json.dumps(provider.calls[1]["messages"], ensure_ascii=False),
        "rendered": json.dumps(
            {
                "events": [event.payload for event in events],
                "prompts": provider.calls,
            },
            ensure_ascii=False,
        ),
    }


def _install_research_provider_stub(monkeypatch) -> None:
    from isotope.capabilities import research as research_capability

    class ProductSmokeResearchProvider:
        provider_name = "codex_delegated"

        def run(self, query: str) -> dict[str, Any]:
            return {
                "research_id": "research_product_smoke",
                "query": query,
                "provider": "codex_delegated",
                "created_at": "2026-06-04T00:00:00Z",
                "status": "ok",
                "evidence_status": "complete",
                "sources": [
                    {
                        "source_id": "source_product_smoke",
                        "title": "Product smoke source",
                        "url": "https://example.com/product-smoke",
                        "snippet": "Research source-backed product smoke result.",
                        "why_used": "integration smoke source",
                        "retrieved_at": "2026-06-04T00:00:00Z",
                    }
                ],
                "report": {
                    "summary": "Research product smoke summary.",
                    "claims": [
                        {
                            "text": "Research source-backed product smoke result.",
                            "source_ids": ["source_product_smoke"],
                            "confidence": "medium",
                        }
                    ],
                    "limitations": [],
                    "next_queries": [],
                },
                "provenance": {"provider": "codex_delegated"},
            }

    monkeypatch.setattr(
        research_capability,
        "build_research_provider",
        lambda provider_id, **kwargs: ProductSmokeResearchProvider(),
    )


def _install_self_repair_launch_stubs(monkeypatch, *, workspace, state_root) -> None:
    def fake_prepare_launch_worktree(*, cwd, target_name, api=None):
        repair_root = workspace / ".worktrees" / "supervisor" / target_name
        repair_root.mkdir(parents=True)
        return {
            "enabled": True,
            "source_cwd": str(cwd),
            "cwd": str(repair_root),
            "worktree_root": str(repair_root),
            "branch": f"codex/{target_name}",
        }

    class FakeRecord:
        name = "desktop-self-repair"
        record_id = "managed-self-repair"
        pid = 12345
        backend = "process"
        worker_role = "self_repair"
        cwd = str(workspace / ".worktrees" / "supervisor" / "desktop-self-repair")
        log_path = str(state_root / "self-repair.log")

    monkeypatch.setattr(
        "isotope.features.supervisor.self_repair.prepare_launch_worktree",
        fake_prepare_launch_worktree,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.self_repair.launch_managed_codex",
        lambda **kwargs: FakeRecord(),
    )


def _detail_labels(payload: dict[str, Any]) -> set[str]:
    return {
        section["label"]
        for section in payload["details"]
        if isinstance(section, dict) and isinstance(section.get("label"), str)
    }
