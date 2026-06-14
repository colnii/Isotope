from __future__ import annotations

import argparse
import json

from isotope.features.social import (
    CharacterCard,
    SocialActionCandidate,
    SocialCapabilityBridge,
    SocialCapabilityRuntimeConfig,
    SocialCapabilityPolicy,
    SocialGroupPolicy,
    SocialOperationsConfig,
    SocialOperationsController,
    SocialRuntime,
    SocialRuntimeConfig,
    qq_runtime_commands,
)
from isotope.integrations.qq import FakeOneBotClient, OneBotAdapter
from tests.unit.features.social.test_character_card import _card_dict


class _FakeCapabilityRunner:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.plan_calls = []
        self.run_calls = []

    def plan_capability_run(self, capability_id, *, inputs=None, env=None):
        self.plan_calls.append((capability_id, dict(inputs or {}), env))
        return {
            "kind": "capability_launch_plan",
            "capability_id": capability_id,
            "can_launch": True,
            "status": "launchable",
            "blocking_reasons": [],
            "missing_inputs": [],
        }

    def run_capability(self, capability_id, *, inputs=None, root_path=None, env=None):
        self.run_calls.append((capability_id, dict(inputs or {}), root_path, env))
        if self.fail:
            raise RuntimeError("fetch failed: https://example.test/page")
        return {
            "kind": "capability_run_result",
            "capability_id": capability_id,
            "status": "completed",
            "answer": "仓库里有 3 个相关测试。",
            "sources": [{"title": "test file", "path": "tests/unit/example.py"}],
        }


class _ContextCapabilityRunner(_FakeCapabilityRunner):
    def run_capability(self, capability_id, *, inputs=None, root_path=None, env=None):
        self.run_calls.append((capability_id, dict(inputs or {}), root_path, env))
        return {
            "kind": "capability_run_result",
            "capability_id": capability_id,
            "status": "completed",
            "context_result": {
                "item_count": 2,
                "items": [
                    {"path": "src/isotope/features/social/runtime.py", "line": 42},
                    {"path": "tests/unit/features/social/test_social.py", "line": 7},
                ],
            },
        }


def _card() -> CharacterCard:
    return CharacterCard.from_dict(_card_dict())


def _candidate(capability_id: str) -> SocialActionCandidate:
    return SocialActionCandidate(
        candidate_id="tool",
        agent_id="agent",
        kind="call_capability",
        reason="needs information",
        confidence=0.8,
        capability_id=capability_id,
    )


def test_capability_bridge_returns_completed_report_for_permitted_capability() -> None:
    runner = _FakeCapabilityRunner()
    report = SocialCapabilityBridge(runner=runner).run(
        _candidate("research.search"),
        character_card=_card(),
        group_id="12345",
        inputs={"query": "pytest"},
    )

    assert report.status == "completed"
    assert report.capability_id == "research.search"
    assert report.content == "仓库里有 3 个相关测试。"
    assert runner.run_calls[0][0] == "research.search"


def test_capability_bridge_blocks_capability_not_allowed_by_role() -> None:
    runner = _FakeCapabilityRunner()
    report = SocialCapabilityBridge(runner=runner).run(
        _candidate("code.apply_patch"),
        character_card=_card(),
        group_id="12345",
        inputs={"patch": "*** Begin Patch\n*** End Patch\n"},
    )

    assert report.status == "blocked"
    assert report.capability_id == "code.apply_patch"
    assert report.reason == "capability_not_allowed_by_role:code.apply_patch"
    assert runner.plan_calls == []
    assert runner.run_calls == []


def test_capability_bridge_reports_runner_failure_with_target_and_error() -> None:
    report = SocialCapabilityBridge(runner=_FakeCapabilityRunner(fail=True)).run(
        _candidate("research.search"),
        character_card=_card(),
        group_id="12345",
        inputs={"query": "https://example.test/page"},
    )

    assert report.status == "failed"
    assert report.target == "research.search"
    assert report.reason == "runner_error:fetch failed: https://example.test/page"
    assert report.content == "research.search failed: fetch failed: https://example.test/page"


def test_capability_bridge_requires_operator_approval_for_risky_capability() -> None:
    runner = _FakeCapabilityRunner()
    bridge = SocialCapabilityBridge(
        runner=runner,
        policy=SocialCapabilityPolicy(
            approval_required_capabilities=("research.search",),
        ),
    )

    report = bridge.run(
        _candidate("research.search"),
        character_card=_card(),
        group_id="12345",
        inputs={"query": "pytest"},
    )

    assert report.status == "requires_operator_approval"
    assert report.reason == "operator_approval_required:research.search"
    assert runner.plan_calls == []
    assert runner.run_calls == []

    approved = bridge.run(
        _candidate("research.search"),
        character_card=_card(),
        group_id="12345",
        inputs={"query": "pytest"},
        operator_approved=True,
    )

    assert approved.status == "completed"
    assert runner.run_calls[0][0] == "research.search"


def test_capability_bridge_summarizes_supervisor_context_result() -> None:
    report = SocialCapabilityBridge(runner=_ContextCapabilityRunner()).run(
        _candidate("supervisor.request_context"),
        character_card=_card(),
        group_id="12345",
        inputs={"query": "capacity", "cwd": "/repo", "state_root": "/state"},
    )

    assert report.status == "completed"
    assert report.content == (
        "找到 2 条相关上下文，最相关：src/isotope/features/social/runtime.py:42。"
    )


def test_social_runtime_sends_approval_prompt_for_capacity_intent() -> None:
    runner = _FakeCapabilityRunner()
    client = FakeOneBotClient()
    client.queue_event(_group_message("10002", "能用一下 isotope capacity 吗"))
    runtime = _runtime_with_capacity_bridge(client=client, runner=runner)

    turn = runtime.process_next(dry_run=False)

    assert turn is not None
    selected = turn.decision.selected if turn.decision is not None else ()
    assert selected[0].kind == "call_capability"
    assert selected[0].capability_id == "supervisor.request_context"
    assert runner.plan_calls == []
    assert runner.run_calls == []
    assert client.sent_group_messages[0]["message"][0]["data"]["text"] == (
        "需要管理员批准后才能调用 supervisor.request_context。"
    )
    assert runtime.operations.health_check()["audit_counts"] == {
        "capability": 1,
        "decision": 1,
        "send": 1,
    }


def test_social_runtime_executes_capacity_intent_when_operator_approves() -> None:
    runner = _FakeCapabilityRunner()
    client = FakeOneBotClient()
    client.queue_event(_group_message("10001", "批准 capacity 查一下项目状态"))
    runtime = _runtime_with_capacity_bridge(client=client, runner=runner)

    turn = runtime.process_next(dry_run=False)

    assert turn is not None
    selected = turn.decision.selected if turn.decision is not None else ()
    assert selected[0].kind == "call_capability"
    assert selected[0].capability_id == "supervisor.request_context"
    assert runner.run_calls == [
        (
            "supervisor.request_context",
            {
                "cwd": "/repo",
                "query": "批准 capacity 查一下项目状态",
                "state_root": "/state",
            },
            None,
            None,
        )
    ]
    assert client.sent_group_messages[0]["message"][0]["data"]["text"] == (
        "仓库里有 3 个相关测试。"
    )
    assert turn.send_feedback[0].sent_message_ids == ("onebot_group_1",)


def test_qq_run_handler_executes_configured_capacity_intent(tmp_path) -> None:
    config_json = tmp_path / "config.json"
    event_json = tmp_path / "event.json"
    state_root = tmp_path / "state"
    config_json.write_text(
        json.dumps(
            {
                "bot_user_id": "bot_qq",
                "group_policy": {
                    "allowed_groups": ["12345"],
                    "blocked_groups": [],
                    "operator_user_ids": ["10001"],
                    "paused_groups": [],
                    "default_dry_run": False,
                },
                "role_card": _card_dict(),
                "runtime": {
                    "capability": {
                        "enabled": True,
                        "capability_id": "supervisor.request_context",
                        "trigger_keywords": ["capacity"],
                        "input_defaults": {
                            "cwd": "/home/lumber/Github/isotope",
                            "state_root": str(tmp_path / "supervisor-state"),
                        },
                        "approval_keywords": ["批准"],
                        "approval_required": True,
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    event_json.write_text(
        json.dumps(_group_message("10001", "批准 capacity 查一下 social runtime")),
        encoding="utf-8",
    )

    payload = qq_runtime_commands.handle_run(
        argparse.Namespace(
            command="run",
            config_json=str(config_json),
            state_root=str(state_root),
            event_json=str(event_json),
            send=True,
        )
    )

    assert payload["status"] == "ok"
    assert payload["turn"]["decision"]["selected"][0]["kind"] == "call_capability"
    assert payload["turn"]["send_feedback"][0]["status"] == "sent"
    sent_text = payload["sent_group_messages"][0]["message"][0]["data"]["text"]
    assert sent_text.startswith("找到 ")
    assert "相关上下文" in sent_text


def _runtime_with_capacity_bridge(
    *,
    client: FakeOneBotClient,
    runner: _FakeCapabilityRunner,
) -> SocialRuntime:
    return SocialRuntime(
        adapter=OneBotAdapter(client=client),
        character_card=_card(),
        operations=SocialOperationsController(
            config=SocialOperationsConfig(
                group_policy=SocialGroupPolicy(
                    allowed_groups=("12345",),
                    operator_user_ids=("10001",),
                )
            )
        ),
        config=SocialRuntimeConfig(
            bot_user_id="bot_qq",
            dry_run=False,
            capability=SocialCapabilityRuntimeConfig(
                enabled=True,
                capability_id="supervisor.request_context",
                trigger_keywords=("capacity",),
                input_defaults={"cwd": "/repo", "state_root": "/state"},
                approval_keywords=("批准",),
            ),
        ),
        capability_bridge=SocialCapabilityBridge(
            runner=runner,
            policy=SocialCapabilityPolicy(
                approval_required_capabilities=("supervisor.request_context",)
            ),
        ),
    )


def _group_message(user_id: str, text: str) -> dict:
    return {
        "message_id": 456,
        "message_type": "group",
        "group_id": 12345,
        "user_id": user_id,
        "sender": {"nickname": "群友", "role": "member"},
        "time": 1780560000,
        "message": [{"type": "text", "data": {"text": text}}],
        "raw_message": text,
    }
