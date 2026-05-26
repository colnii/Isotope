from __future__ import annotations

import pytest

from isotope.platform.registry.actions import ActionTypeRegistry
from isotope.policy import PolicyEngine
from isotope.runtime.in_process.action_compiler import ActionCompiler


def _runtime_context(*, requires_approval: bool = False) -> dict[str, object]:
    return {
        "run_id": "run_screen",
        "agent_id": "agent_supervisor",
        "thread_id": "thread_main",
        "requires_approval": requires_approval,
    }


def _observe_intent() -> dict:
    return {
        "action": "call_tool",
        "tool": "screen_observe",
        "target_selector": {
            "kind": "window",
            "selector": {"app": "notepad.exe"},
        },
        "mode": "non_intrusive",
        "capture": ["metadata", "screenshot"],
        "summary": "observe target",
    }


def _control_intent(*, execution_mode: str = "execute") -> dict:
    return {
        "action": "call_tool",
        "tool": "screen_control",
        "target_selector": {
            "kind": "window",
            "selector": {"app": "notepad.exe"},
        },
        "mode": "interactive",
        "execution_mode": execution_mode,
        "actions": [{"type": "click", "button": "left", "x": 5, "y": 6}],
        "summary": "control target",
    }


def test_default_registry_exposes_screen_tools_with_screen_capabilities():
    registry = ActionTypeRegistry.default()

    assert "screen_observe" in registry.tool_names()
    assert "screen_control" in registry.tool_names()
    observe = registry.get_tool("screen_observe")
    control = registry.get_tool("screen_control")
    assert observe.required_capabilities["screen"]["observe"] is True
    assert observe.required_capabilities["screen"]["control"] is False
    assert control.required_capabilities["screen"]["observe"] is True
    assert control.required_capabilities["screen"]["control"] is True
    assert control.required_capabilities["screen"]["action_policy"]["execution_modes"] == ["dry_run"]


def test_action_compiler_carries_screen_payload_without_raw_input_in_capabilities():
    compiler = ActionCompiler(registry=ActionTypeRegistry.default())

    proposal = compiler.compile(_control_intent(execution_mode="dry_run"), _runtime_context())

    assert proposal.payload["tool"] == "screen_control"
    assert proposal.payload["target_selector"]["selector"]["app"] == "notepad.exe"
    assert proposal.payload["actions"] == [{"type": "click", "button": "left", "x": 5, "y": 6}]
    assert proposal.payload["approval_requested"] is False
    assert proposal.requested_capabilities == {
        "tools": ["screen_control"],
        "workspace": {"mode": "shared_ro"},
        "budget": {"seconds": 5},
    }


def test_policy_grants_screen_observe_with_artifact_policy():
    compiler = ActionCompiler(registry=ActionTypeRegistry.default())
    proposal = compiler.compile(_observe_intent(), _runtime_context())

    decision = PolicyEngine(registry=ActionTypeRegistry.default()).decide(proposal)

    assert decision.outcome == "approved"
    assert decision.grants["tools"] == ["screen_observe"]
    assert decision.grants["screen"]["observe"] is True
    assert decision.grants["screen"]["control"] is False
    assert decision.grants["screen"]["artifact_policy"]["full_content_in_events"] is False


def test_policy_denies_execute_control_without_approval():
    compiler = ActionCompiler(registry=ActionTypeRegistry.default())
    proposal = compiler.compile(_control_intent(execution_mode="execute"), _runtime_context())

    decision = PolicyEngine(registry=ActionTypeRegistry.default()).decide(proposal)

    assert decision.outcome == "denied"
    assert decision.reason_codes == ["screen_approval_required"]


def test_policy_allows_execute_control_when_approval_requested():
    compiler = ActionCompiler(registry=ActionTypeRegistry.default())
    proposal = compiler.compile(
        _control_intent(execution_mode="execute"),
        _runtime_context(requires_approval=True),
    )

    decision = PolicyEngine(registry=ActionTypeRegistry.default()).decide(proposal)

    assert decision.outcome == "approved"
    assert decision.grants["tools"] == ["screen_control"]
    assert decision.grants["screen"]["control"] is True
    assert "execute" in decision.grants["screen"]["action_policy"]["execution_modes"]


def test_policy_denies_unknown_screen_action_type_before_executor():
    compiler = ActionCompiler(registry=ActionTypeRegistry.default())
    intent = _control_intent(execution_mode="dry_run")
    intent["actions"] = [{"type": "unknown"}]

    with pytest.raises(ValueError, match="screen action type"):
        compiler.compile(intent, _runtime_context())
