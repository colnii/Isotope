from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from isotope import events, projector


RUN_ID = "run_001"

KNOWN_CANONICAL_EVENT_TYPES = {
    "run.created",
    "run.completed",
    "agent.created",
    "action.proposed",
    "action.decided",
    "action.started",
    "action.completed",
    "action.failed",
    "artifact.created",
    "approval.requested",
    "approval.resolved",
    "memory.record_created",
    "memory.record_superseded",
    "snapshot.imported",
    "delegation.proposed",
    "delegation.decided",
    "worker.created",
    "worker.started",
    "worker.completed",
    "worker.failed",
    "worker.cancelled",
    "worker.result_handed_off",
    "workspace.bound",
    "workspace.lease_created",
    "workspace.released",
    "workspace.artifact_captured",
    "action.retry_requested",
    "action.retry_created",
    "action.cancel_requested",
    "action.cancelled",
    "action.superseded",
}


def _event(event_id: str, event_type: str, payload: dict) -> events.CanonicalEvent:
    return events.CanonicalEvent(
        event_id=event_id,
        run_id=RUN_ID,
        event_type=event_type,
        payload=payload,
        created_at=f"2026-05-05T00:00:{event_id[-2:]}Z",
    )


def test_event_schema_registry_module_exists_and_exposes_default_registry():
    event_schema = importlib.import_module("isotope.event_schema")

    registry = event_schema.EventSchemaRegistry.default()

    assert registry.registry_id == "isotope"
    assert registry.registry_version
    assert registry.get("run.created").event_type == "run.created"
    assert registry.get("run.created").event_schema_version


def test_every_known_canonical_event_type_has_registered_schema_metadata():
    event_schema = importlib.import_module("isotope.event_schema")
    registry = event_schema.EventSchemaRegistry.default()

    missing = [event_type for event_type in sorted(KNOWN_CANONICAL_EVENT_TYPES) if registry.get(event_type) is None]

    assert missing == []
    for event_type in KNOWN_CANONICAL_EVENT_TYPES:
        metadata = registry.get(event_type)
        assert metadata.event_type == event_type
        assert metadata.event_schema_version
        assert isinstance(metadata.required_fields, tuple)
        assert metadata.validation_owner in {"registry", "projector"}


def test_projector_rejects_unknown_event_type_without_advancing_last_event_id():
    canonical_events = [
        _event("evt_001", "run.created", {"run_id": RUN_ID}),
        _event(
            "evt_002",
            "provider.future_event",
            {
                "event_schema_version": "provider.future_event@v1",
                "summary": "unknown future payload",
            },
        ),
    ]

    with pytest.raises(ValueError, match="unknown event_type|unsupported event"):
        projector.RunProjector().project(canonical_events)


def test_unknown_event_type_error_is_controlled_and_diagnosable():
    unknown = _event(
        "evt_001",
        "plugin.custom_event",
        {"event_schema_version": "plugin.custom_event@v1"},
    )

    with pytest.raises(ValueError) as exc_info:
        projector.RunProjector().project([unknown])

    message = str(exc_info.value)
    assert "event_type" in message
    assert "plugin.custom_event" in message


def test_event_schema_boundary_does_not_add_schema_runtime_dependencies():
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")

    forbidden_dependency_names = ("jsonschema", "protobuf", "avro")

    for dependency_name in forbidden_dependency_names:
        assert dependency_name not in pyproject.lower()
