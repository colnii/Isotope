from __future__ import annotations

import pytest

import isotope.runtime.action_compiler as action_compiler
import isotope.platform.registry.actions as action_registry
import isotope.platform.events.events as events
import isotope.platform.state.projector as projector
import isotope.runtime.in_process as server


RUN_ID = "run_001"


def _runtime_context(**overrides):
    context = {
        "run_id": RUN_ID,
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


def _event(event_id: str, event_type: str, payload: dict):
    return events.CanonicalEvent(
        event_id=event_id,
        run_id=RUN_ID,
        event_type=event_type,
        payload=payload,
        created_at=f"2026-05-03T00:00:{event_id[-2:]}Z",
    )


def test_default_action_registry_exposes_stable_version_basis():
    registry = action_registry.ActionTypeRegistry.default()

    assert registry.registry_id == "default"
    assert isinstance(registry.registry_version, str)
    assert registry.registry_version


def test_custom_action_registry_accepts_explicit_version_metadata():
    registry = action_registry.ActionTypeRegistry(
        entries=[_registry_entry()],
        registry_id="demo_registry",
        registry_version="demo_registry@v1",
    )

    assert registry.registry_id == "demo_registry"
    assert registry.registry_version == "demo_registry@v1"


def test_malformed_action_registry_version_metadata_fails_fast():
    with pytest.raises(ValueError, match="registry_id"):
        action_registry.ActionTypeRegistry(
            entries=[_registry_entry()],
            registry_id="",
            registry_version="demo_registry@v1",
        )

    with pytest.raises(ValueError, match="registry_version"):
        action_registry.ActionTypeRegistry(
            entries=[_registry_entry()],
            registry_id="demo_registry",
            registry_version="",
        )


def test_action_compiler_embeds_registry_basis_into_proposal():
    registry = action_registry.ActionTypeRegistry(
        entries=[_registry_entry()],
        registry_id="demo_registry",
        registry_version="demo_registry@v1",
    )
    proposal = action_compiler.ActionCompiler(registry=registry).compile(
        _intent(),
        _runtime_context(),
    )

    assert proposal.registry_id == "demo_registry"
    assert proposal.registry_version == "demo_registry@v1"
    assert proposal.registry_basis == {
        "registry_id": "demo_registry",
        "registry_version": "demo_registry@v1",
    }


def test_server_action_proposed_event_includes_registry_basis(tmp_path):
    api = server.InProcessServer(tmp_path)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="registry basis demo")

    api.submit_action(run["run_id"], _intent())

    proposed = next(
        event.payload
        for event in api.get_events(run["run_id"])
        if event.event_type == "action.proposed"
    )
    assert proposed["registry_id"] == api.compiler.registry.registry_id
    assert proposed["registry_version"] == api.compiler.registry.registry_version


def test_action_proposed_payload_missing_registry_basis_fails_fast():
    canonical_events = [
        _event("evt_001", "run.created", {"run_id": RUN_ID}),
        _event(
            "evt_002",
            "action.proposed",
                {
                    "proposal_id": "prop_001",
                    "agent_id": "agent_supervisor",
                    "action_type": "call_tool",
                },
            ),
        ]

    with pytest.raises(ValueError, match="registry"):
        projector.RunProjector().project(canonical_events)


def test_projector_exposes_registry_basis_from_event_payload_without_default_registry(monkeypatch):
    monkeypatch.setattr(
        action_registry.ActionTypeRegistry,
        "default",
        classmethod(lambda cls: pytest.fail("projector replay must not consult current default registry")),
    )
    canonical_events = [
        _event("evt_001", "run.created", {"run_id": RUN_ID}),
        _event(
            "evt_002",
            "action.proposed",
            {
                "proposal_id": "prop_001",
                "agent_id": "agent_supervisor",
                "action_type": "call_tool",
                "registry_id": "demo_registry",
                "registry_version": "demo_registry@v1",
                "registry_basis": {
                    "registry_id": "demo_registry",
                    "registry_version": "demo_registry@v1",
                },
            },
        ),
        _event(
            "evt_003",
            "action.decided",
                {
                    "proposal_id": "prop_001",
                    "decision_id": "dec_001",
                    "outcome": "denied",
                    "reason_codes": ["unsupported_tool"],
                    "policy_profile_id": "default",
                    "policy_version": "v0.2",
                },
            ),
        ]

    state = projector.RunProjector().project(canonical_events)

    assert state.actions["prop_001"]["registry_id"] == "demo_registry"
    assert state.actions["prop_001"]["registry_version"] == "demo_registry@v1"
    assert state.actions["prop_001"]["registry_basis"] == {
        "registry_id": "demo_registry",
        "registry_version": "demo_registry@v1",
    }


def test_unknown_action_type_still_fails_closed_at_compiler_boundary():
    compiler = action_compiler.ActionCompiler()

    with pytest.raises(ValueError, match="unsupported compact action"):
        compiler.compile(_intent(action="delete_world"), _runtime_context())


def test_registry_entry_cannot_carry_executable_plugin_callback():
    entry = action_registry.ActionTypeEntry.from_dict(
        _registry_entry(handler=lambda: "side effect", entry_version="tool@v1")
    )

    assert not hasattr(entry, "handler")
    assert not hasattr(action_registry, "PluginMarketplace")
    assert not hasattr(action_registry.ActionTypeRegistry, "load_remote")
