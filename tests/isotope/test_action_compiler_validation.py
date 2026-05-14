import pytest

from isotope import action_compiler, models


def _compiler():
    return action_compiler.ActionCompiler()


def _runtime_context(**overrides):
    context = {
        "run_id": "run_001",
        "agent_id": "agent_supervisor",
        "thread_id": "thread_main",
    }
    context.update(overrides)
    return context


def _intent(**overrides):
    intent = {
        "action": "call_tool",
        "tool": "write_artifact_tool",
    }
    intent.update(overrides)
    return intent


def test_compile_rejects_non_dict_intent():
    with pytest.raises(ValueError, match="intent must be a dict"):
        _compiler().compile(["not", "dict"], _runtime_context())


def test_compile_rejects_non_dict_runtime_context():
    with pytest.raises(ValueError, match="runtime_context must be a dict"):
        _compiler().compile(_intent(), ["not", "dict"])


@pytest.mark.parametrize("field", ["run_id", "agent_id", "thread_id"])
@pytest.mark.parametrize("bad_value", [None, "", 123])
def test_compile_rejects_invalid_runtime_identity_fields(field, bad_value):
    context = _runtime_context(**{field: bad_value})

    with pytest.raises(ValueError, match=f"runtime_context.{field} must be a non-empty string"):
        _compiler().compile(_intent(), context)


@pytest.mark.parametrize("intent", [{}, {"action": "emit_artifact"}, {"action": 123}])
def test_compile_rejects_missing_or_non_call_tool_action(intent):
    with pytest.raises(ValueError, match="unsupported compact action"):
        _compiler().compile(intent, _runtime_context())


@pytest.mark.parametrize("bad_tool", [None, "", 123])
def test_compile_rejects_missing_empty_or_non_string_tool(bad_tool):
    with pytest.raises(ValueError, match="compact intent requires a tool"):
        _compiler().compile(_intent(tool=bad_tool), _runtime_context())


def test_compile_rejects_non_list_requested_tools():
    with pytest.raises(ValueError, match="requested_tools must be a list"):
        _compiler().compile(_intent(requested_tools="write_artifact_tool"), _runtime_context())


def test_compile_rejects_non_string_workspace_mode():
    with pytest.raises(ValueError, match="workspace_mode must be a string"):
        _compiler().compile(_intent(workspace_mode=123), _runtime_context())


@pytest.mark.parametrize("seconds", ["many", -1, 1.5])
def test_compile_rejects_invalid_budget_seconds(seconds):
    with pytest.raises(ValueError, match="budget.seconds must be a non-negative integer"):
        _compiler().compile(_intent(budget={"seconds": seconds}), _runtime_context())


def test_valid_minimal_intent_compiles_to_action_proposal():
    proposal = _compiler().compile(_intent(), _runtime_context())

    assert isinstance(proposal, models.ActionProposal)
    assert proposal.action_type == "call_tool"
    assert proposal.payload == {"tool": "write_artifact_tool", "text": ""}
    assert proposal.requested_capabilities == {
        "tools": ["write_artifact_tool"],
        "workspace": {"mode": "shared_ro"},
        "budget": {"seconds": 30},
    }


def test_compile_uses_runtime_context_identity_not_intent_identity():
    proposal = _compiler().compile(
        _intent(
            run_id="intent_run",
            agent_id="intent_agent",
            thread_id="intent_thread",
        ),
        _runtime_context(
            run_id="runtime_run",
            agent_id="runtime_agent",
            thread_id="runtime_thread",
        ),
    )

    assert proposal.run_id == "runtime_run"
    assert proposal.agent_id == "runtime_agent"
    assert proposal.thread_id == "runtime_thread"
