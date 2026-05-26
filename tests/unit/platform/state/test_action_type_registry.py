import importlib

import pytest


def _registry_module():
    return importlib.import_module("isotope.platform.registry.actions")


def _registry_class():
    return getattr(_registry_module(), "ActionTypeRegistry")


def _default_registry():
    return _registry_class().default()


def _valid_entry(**overrides):
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


def test_action_registry_module_exists():
    module = _registry_module()

    assert module.__name__ == "isotope.platform.registry.actions"


def test_action_type_registry_class_exists():
    assert hasattr(_registry_module(), "ActionTypeRegistry")


def test_default_registry_contains_current_controlled_tool_slices():
    registry = _default_registry()

    assert registry.tool_names() == [
        "write_artifact_tool",
        "write_memory",
        "terminal_exec",
        "screen_observe",
        "screen_control",
    ]
    entry = registry.get_tool("write_artifact_tool")
    assert entry.action_type == "call_tool"
    assert entry.tool_name == "write_artifact_tool"
    memory_entry = registry.get_tool("write_memory")
    assert memory_entry.action_type == "write_memory"
    assert memory_entry.result_kind == "memory_record"
    terminal_entry = registry.get_tool("terminal_exec")
    assert terminal_entry.action_type == "call_tool"
    assert terminal_entry.tool_name == "terminal_exec"
    assert registry.get_tool("screen_observe").result_kind == "screen_observation"
    assert registry.get_tool("screen_control").result_kind == "screen_control_result"


def test_default_registry_gets_write_artifact_tool_entry():
    entry = _default_registry().get_tool("write_artifact_tool")

    assert entry.action_type == "call_tool"
    assert entry.tool_name == "write_artifact_tool"
    assert entry.enabled is True


def test_unknown_tool_lookup_fails_closed():
    registry = _default_registry()

    with pytest.raises(KeyError, match="unknown_tool"):
        registry.get_tool("unknown_tool")


def test_registry_entry_exposes_v0_candidate_metadata():
    entry = _default_registry().get_tool("write_artifact_tool")

    assert entry.action_type == "call_tool"
    assert entry.tool_name == "write_artifact_tool"
    assert isinstance(entry.required_capabilities, dict)
    assert entry.default_workspace_mode == "shared_ro"
    assert entry.result_kind == "artifact"
    assert entry.enabled is True


def test_write_artifact_tool_required_capabilities_match_current_slice():
    entry = _default_registry().get_tool("write_artifact_tool")

    assert entry.required_capabilities == {
        "tools": ["write_artifact_tool"],
        "workspace": {"mode": "shared_ro"},
        "budget": {"seconds": 30},
    }


@pytest.mark.parametrize(
    "entry",
    [
        pytest.param(
            {
                "tool_name": "write_artifact_tool",
                "required_capabilities": {"tools": ["write_artifact_tool"]},
                "default_workspace_mode": "shared_ro",
                "result_kind": "artifact",
                "enabled": True,
            },
            id="missing-action-type",
        ),
        pytest.param(
            {
                "action_type": "call_tool",
                "required_capabilities": {"tools": ["write_artifact_tool"]},
                "default_workspace_mode": "shared_ro",
                "result_kind": "artifact",
                "enabled": True,
            },
            id="missing-tool-name",
        ),
        pytest.param(_valid_entry(enabled="yes"), id="enabled-not-bool"),
        pytest.param(_valid_entry(required_capabilities=["tools"]), id="capabilities-not-dict"),
    ],
)
def test_malformed_registry_entries_fail_fast(entry):
    with pytest.raises(ValueError):
        _registry_class()(entries=[entry])


def test_registry_rejects_non_dict_entry():
    with pytest.raises(ValueError):
        _registry_class()(entries=["not-a-dict"])


def test_registry_entry_does_not_carry_executable_side_effect_callbacks():
    entry = _default_registry().get_tool("write_artifact_tool")

    for forbidden_name in ("execute", "append_event", "write_artifact"):
        assert not callable(getattr(entry, forbidden_name, None))
