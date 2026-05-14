import pytest

from isotope import models, policy


def _proposal(**overrides):
    values = {
        "proposal_id": "prop_001",
        "run_id": "run_001",
        "agent_id": "agent_supervisor",
        "thread_id": "thread_main",
        "action_type": "call_tool",
        "payload": {"tool": "write_artifact_tool", "text": "hello"},
        "requested_capabilities": {
            "tools": ["write_artifact_tool"],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": 30},
        },
    }
    values.update(overrides)
    return models.ActionProposal(**values)


def test_policy_rejects_non_action_proposal():
    with pytest.raises(TypeError, match="ActionProposal"):
        policy.PolicyEngine().decide({"action_type": "call_tool"})


def test_policy_rejects_non_dict_payload():
    proposal = _proposal(payload=["not", "dict"])

    with pytest.raises(TypeError, match="proposal payload must be a dict"):
        policy.PolicyEngine().decide(proposal)


def test_policy_rejects_non_dict_requested_capabilities():
    proposal = _proposal(requested_capabilities=["not", "dict"])

    with pytest.raises(TypeError, match="requested_capabilities must be a dict"):
        policy.PolicyEngine().decide(proposal)


def test_policy_rejects_non_list_requested_tools():
    proposal = _proposal(
        requested_capabilities={
            "tools": "write_artifact_tool",
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": 30},
        }
    )

    with pytest.raises(TypeError, match="requested tools must be a list"):
        policy.PolicyEngine().decide(proposal)


def test_policy_rejects_negative_budget():
    proposal = _proposal(
        requested_capabilities={
            "tools": ["write_artifact_tool"],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": -1},
        }
    )

    with pytest.raises(ValueError, match="budget.seconds must be non-negative"):
        policy.PolicyEngine().decide(proposal)


def test_policy_rejects_non_int_like_budget():
    proposal = _proposal(
        requested_capabilities={
            "tools": ["write_artifact_tool"],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": "many"},
        }
    )

    with pytest.raises(ValueError, match="budget.seconds must be int-like"):
        policy.PolicyEngine().decide(proposal)


def test_policy_decision_outcome_is_known_value():
    engine = policy.PolicyEngine()
    decisions = [
        engine.decide(_proposal()),
        engine.decide(_proposal(requested_capabilities={
            "tools": ["write_artifact_tool", "extra_tool"],
            "workspace": {"mode": "isolated_rw"},
            "budget": {"seconds": 999},
        })),
        engine.decide(_proposal(payload={"tool": "unsupported_tool"})),
    ]

    assert {decision.outcome for decision in decisions} <= {"approved", "modified", "denied"}


def test_denied_decision_has_no_effective_grants():
    decision = policy.PolicyEngine().decide(_proposal(payload={"tool": "unsupported_tool"}))

    assert decision.outcome == "denied"
    assert decision.grants["tools"] == []
    assert decision.grants["workspace"]["mode"] == "none"
    assert decision.grants["budget"]["seconds"] == 0


def test_approved_or_modified_decision_has_required_grants():
    engine = policy.PolicyEngine()
    decisions = [
        engine.decide(_proposal()),
        engine.decide(_proposal(requested_capabilities={
            "tools": ["write_artifact_tool", "extra_tool"],
            "workspace": {"mode": "isolated_rw"},
            "budget": {"seconds": 999},
        })),
    ]

    assert {decision.outcome for decision in decisions} == {"approved", "modified"}
    for decision in decisions:
        assert decision.grants["tools"] == ["write_artifact_tool"]
        assert decision.grants["workspace"]["mode"] == "shared_ro"
        assert isinstance(decision.grants["budget"]["seconds"], int)
