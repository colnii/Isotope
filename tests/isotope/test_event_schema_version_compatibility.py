from __future__ import annotations

from pathlib import Path

import pytest

import isotope.platform.events.events as events
import isotope.platform.state.projector as projector


RUN_ID = "run_001"
ARTIFACT_REF = {
    "ref_type": "artifact",
    "scope": "run",
    "run_id": RUN_ID,
    "artifact_id": "artifact_001",
}


def _event(event_id: str, event_type: str, payload: dict, **overrides) -> events.CanonicalEvent:
    kwargs = {
        "event_id": event_id,
        "run_id": RUN_ID,
        "event_type": event_type,
        "payload": payload,
        "created_at": f"2026-05-05T00:00:{event_id[-2:]}Z",
    }
    kwargs.update(overrides)
    return events.CanonicalEvent(**kwargs)


def _checkpoint_events() -> list[events.CanonicalEvent]:
    return [
        _event("evt_001", "run.created", {"run_id": RUN_ID}),
        _event("evt_002", "agent.created", {"agent_id": "agent_supervisor"}),
        _event(
            "evt_003",
            "action.proposed",
            {
                "proposal_id": "prop_001",
                "agent_id": "agent_supervisor",
                "action_type": "call_tool",
                "registry_id": "default",
                "registry_version": "v0.2",
            },
        ),
        _event(
            "evt_004",
            "action.decided",
            {
                "decision_id": "dec_001",
                "proposal_id": "prop_001",
                "outcome": "approved",
                "policy_profile_id": "default",
                "policy_version": "v0.2",
            },
        ),
        _event(
            "evt_005",
            "action.started",
            {
                "execution_id": "exec_001",
                "proposal_id": "prop_001",
                "decision_id": "dec_001",
            },
        ),
        _event(
            "evt_006",
            "artifact.created",
            {
                "artifact": {
                    "ref": ARTIFACT_REF,
                    "artifact_type": "text",
                    "summary": "hello artifact",
                    "provenance": {"execution_id": "exec_001", "proposal_id": "prop_001", "decision_id": "dec_001"},
                }
            },
        ),
        _event(
            "evt_007",
            "action.completed",
            {
                "execution_id": "exec_001",
                "status": "completed",
                "artifact_refs": [ARTIFACT_REF],
            },
        ),
        _event("evt_008", "run.completed", {"status": "completed"}),
    ]


def test_event_envelope_version_and_payload_schema_version_are_separate():
    event = _event(
        "evt_001",
        "run.created",
        {"run_id": RUN_ID, "event_schema_version": "run.created@slice_v0"},
    )

    assert event.event_envelope_version == events.EVENT_ENVELOPE_VERSION
    assert event.payload["event_schema_version"] == "run.created@slice_v0"
    assert event.payload["event_schema_version"] != event.event_envelope_version


def test_unsupported_event_envelope_version_fails_closed():
    with pytest.raises(ValueError, match="event_envelope_version"):
        _event(
            "evt_001",
            "run.created",
            {"run_id": RUN_ID},
            event_envelope_version="canonical_event_slice@future",
        )


def test_unsupported_event_payload_schema_version_fails_closed():
    canonical_events = [
        _event(
            "evt_001",
            "run.created",
            {
                "run_id": RUN_ID,
                "event_schema_version": "run.created@future",
            },
        )
    ]

    with pytest.raises(ValueError, match="event_schema_version|unsupported schema"):
        projector.RunProjector().project(canonical_events)


def test_missing_required_event_schema_version_for_new_event_fails_closed():
    canonical_events = [
        _event("evt_001", "run.created", {"run_id": RUN_ID}),
        _event("evt_002", "event_schema.demo_new_event", {"summary": "missing schema version"}),
    ]

    with pytest.raises(ValueError, match="event_schema_version|unknown event_type"):
        projector.RunProjector().project(canonical_events)


def test_known_required_field_validation_still_fails_fast():
    canonical_events = [
        _event("evt_001", "run.created", {"run_id": RUN_ID}),
        _event(
            "evt_002",
            "action.proposed",
            {
                "proposal_id": "prop_001",
                "agent_id": "agent_supervisor",
                "action_type": "call_tool",
                "registry_id": "default",
            },
        ),
    ]

    with pytest.raises(ValueError, match="registry_version"):
        projector.RunProjector().project(canonical_events)


def test_checkpoint_schema_version_remains_separate_from_event_schema_version():
    checkpoint = projector.RunProjector().create_checkpoint(RUN_ID, _checkpoint_events())

    assert checkpoint["projector_version"].startswith("run_projector@")
    assert checkpoint["integrity"]["event_digest_event_envelope_version"] == events.EVENT_ENVELOPE_VERSION
    assert "event_schema_version" not in checkpoint
    assert "event_schema_version" not in checkpoint["integrity"]


def test_event_schema_boundary_does_not_add_overreach_dependencies_or_modules():
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8").lower()
    source_files = "\n".join(path.name for path in Path("src/isotope").glob("*.py")).lower()

    for forbidden in ("jsonschema", "protobuf", "avro"):
        assert forbidden not in pyproject
    for forbidden_module_name in ("migration", "plugin_event", "remote_schema"):
        assert forbidden_module_name not in source_files
