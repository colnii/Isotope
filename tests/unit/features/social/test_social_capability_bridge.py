from __future__ import annotations

from isotope.features.social import (
    CharacterCard,
    SocialActionCandidate,
    SocialCapabilityBridge,
    SocialCapabilityPolicy,
)
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
