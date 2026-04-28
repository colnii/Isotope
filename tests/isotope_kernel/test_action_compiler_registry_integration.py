import pytest

from isotope_kernel import action_compiler, action_registry, models


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
        "text": "hello",
    }
    intent.update(overrides)
    return intent


def _registry_entry(**overrides):
    entry = {
        "action_type": "call_tool",
        "tool_name": "write_artifact_tool",
        "payload_requirements": {"required": ["text"]},
        "required_capabilities": {
            "tools": ["write_artifact_tool"],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": 30},
        },
        "default_workspace_mode": "shared_ro",
        "result_kind": "artifact",
        "enabled": True,
    }
    entry.update(overrides)
    return entry


def test_action_compiler_accepts_explicit_registry():
    compiler = action_compiler.ActionCompiler(registry=action_registry.ActionTypeRegistry.default())

    assert isinstance(compiler, action_compiler.ActionCompiler)


def test_explicit_registry_allows_write_artifact_tool_to_compile():
    compiler = action_compiler.ActionCompiler(registry=action_registry.ActionTypeRegistry.default())

    proposal = compiler.compile(_intent(), _runtime_context())

    assert isinstance(proposal, models.ActionProposal)
    assert proposal.action_type == "call_tool"
    assert proposal.payload == {"tool": "write_artifact_tool", "text": "hello"}


def test_default_registry_allows_write_artifact_tool_to_compile():
    proposal = action_compiler.ActionCompiler().compile(_intent(), _runtime_context())

    assert isinstance(proposal, models.ActionProposal)
    assert proposal.action_type == "call_tool"
    assert proposal.payload["tool"] == "write_artifact_tool"


def test_unknown_tool_fails_closed_at_compiler_boundary():
    compiler = action_compiler.ActionCompiler()

    with pytest.raises(ValueError, match="unknown tool"):
        compiler.compile(_intent(tool="unknown_tool"), _runtime_context())


def test_disabled_registry_entry_is_rejected_by_compiler():
    registry = action_registry.ActionTypeRegistry(
        entries=[_registry_entry(enabled=False)]
    )
    compiler = action_compiler.ActionCompiler(registry=registry)

    with pytest.raises(ValueError, match="disabled tool"):
        compiler.compile(_intent(), _runtime_context())


def test_compiler_uses_default_registry_when_registry_is_not_provided(monkeypatch):
    disabled_default_registry = action_registry.ActionTypeRegistry(
        entries=[_registry_entry(enabled=False)]
    )
    monkeypatch.setattr(
        action_registry.ActionTypeRegistry,
        "default",
        classmethod(lambda cls: disabled_default_registry),
    )

    with pytest.raises(ValueError, match="disabled tool"):
        action_compiler.ActionCompiler().compile(_intent(), _runtime_context())


def test_compiler_generates_requested_capabilities_not_grants():
    proposal = action_compiler.ActionCompiler().compile(_intent(), _runtime_context())

    assert proposal.requested_capabilities == {
        "tools": ["write_artifact_tool"],
        "workspace": {"mode": "shared_ro"},
        "budget": {"seconds": 30},
    }
    assert not hasattr(proposal, "grants")


def test_compiler_uses_runtime_context_identity_not_intent_identity_with_registry():
    proposal = action_compiler.ActionCompiler().compile(
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
