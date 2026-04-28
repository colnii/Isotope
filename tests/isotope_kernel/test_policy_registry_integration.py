import pytest

from isotope_kernel import action_registry, models, policy


def _proposal(
    *,
    tool: str = "write_artifact_tool",
    requested_tools: list[str] | None = None,
    workspace_mode: str = "shared_ro",
    budget_seconds: int = 30,
) -> models.ActionProposal:
    if requested_tools is None:
        requested_tools = [tool]
    return models.ActionProposal(
        proposal_id="prop_001",
        run_id="run_001",
        agent_id="agent_supervisor",
        thread_id="thread_main",
        action_type="call_tool",
        payload={"tool": tool, "text": "hello"},
        requested_capabilities={
            "tools": requested_tools,
            "workspace": {"mode": workspace_mode},
            "budget": {"seconds": budget_seconds},
        },
    )


def _registry_entry(tool_name: str, **overrides) -> dict:
    entry = {
        "action_type": "call_tool",
        "tool_name": tool_name,
        "payload_requirements": {"required": ["text"]},
        "required_capabilities": {
            "tools": [tool_name],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": 30},
        },
        "default_workspace_mode": "shared_ro",
        "result_kind": "artifact",
        "enabled": True,
    }
    entry.update(overrides)
    return entry


def _registry_for_tools(*tool_names: str) -> action_registry.ActionTypeRegistry:
    return action_registry.ActionTypeRegistry(
        entries=[_registry_entry(tool_name) for tool_name in tool_names]
    )


def test_policy_engine_accepts_explicit_registry():
    engine = policy.PolicyEngine(registry=action_registry.ActionTypeRegistry.default())

    assert isinstance(engine, policy.PolicyEngine)


def test_default_policy_still_approves_write_artifact_tool():
    decision = policy.PolicyEngine().decide(_proposal())

    assert decision.outcome == "approved"
    assert decision.grants == {
        "tools": ["write_artifact_tool"],
        "workspace": {"mode": "shared_ro"},
        "budget": {"seconds": 30},
    }


def test_policy_uses_default_registry_when_registry_not_provided(monkeypatch):
    registry = _registry_for_tools("write_report_tool")
    monkeypatch.setattr(
        action_registry.ActionTypeRegistry,
        "default",
        classmethod(lambda cls: registry),
    )

    decision = policy.PolicyEngine().decide(
        _proposal(tool="write_report_tool", requested_tools=["write_report_tool"])
    )

    assert decision.outcome == "approved"
    assert decision.grants["tools"] == ["write_report_tool"]


def test_policy_uses_registry_tool_requirement_for_known_test_tool():
    engine = policy.PolicyEngine(registry=_registry_for_tools("write_report_tool"))

    decision = engine.decide(
        _proposal(tool="write_report_tool", requested_tools=["write_report_tool"])
    )

    assert decision.outcome == "approved"
    assert decision.grants == {
        "tools": ["write_report_tool"],
        "workspace": {"mode": "shared_ro"},
        "budget": {"seconds": 30},
    }


def test_registry_entry_does_not_auto_approve_unrequested_tool():
    engine = policy.PolicyEngine(registry=_registry_for_tools("write_report_tool"))

    decision = engine.decide(
        _proposal(tool="write_report_tool", requested_tools=[])
    )

    assert decision.outcome == "denied"
    assert decision.grants == {
        "tools": [],
        "workspace": {"mode": "none"},
        "budget": {"seconds": 0},
    }


def test_policy_reduces_requested_capabilities_for_registry_tool():
    engine = policy.PolicyEngine(registry=_registry_for_tools("write_report_tool"))

    decision = engine.decide(
        _proposal(
            tool="write_report_tool",
            requested_tools=["write_report_tool", "extra_tool"],
            workspace_mode="isolated_rw",
            budget_seconds=999,
        )
    )

    assert decision.outcome == "modified"
    assert decision.grants == {
        "tools": ["write_report_tool"],
        "workspace": {"mode": "shared_ro"},
        "budget": {"seconds": 30},
    }


def test_registry_cannot_expand_grants_to_unrequested_registered_tool():
    engine = policy.PolicyEngine(
        registry=_registry_for_tools("write_report_tool", "extra_tool")
    )

    decision = engine.decide(
        _proposal(tool="write_report_tool", requested_tools=["write_report_tool"])
    )

    assert decision.outcome == "approved"
    assert decision.grants["tools"] == ["write_report_tool"]
    assert "extra_tool" not in decision.grants["tools"]
