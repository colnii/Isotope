from __future__ import annotations

import pytest

from isotope.features.supervisor.commands.snapshot_display import (
    DEGRADED_SNAPSHOT_SCHEMA_LABEL,
    state_snapshot_schema_display,
    state_snapshot_schema_label,
    state_snapshot_schema_status,
)


@pytest.mark.parametrize(
    ("snapshot", "expected"),
    [
        (
            {"kind": "supervisor_state_snapshot", "schema_version": 1},
            {
                "schema_label": "supervisor_state_snapshot v1",
                "schema_status": "ok",
                "schema_reason": None,
            },
        ),
        (
            {"schema_version": 1},
            {
                "schema_label": DEGRADED_SNAPSHOT_SCHEMA_LABEL,
                "schema_status": "degraded",
                "schema_reason": "missing kind",
            },
        ),
        (
            {"kind": "supervisor_state_snapshot"},
            {
                "schema_label": "supervisor_state_snapshot degraded",
                "schema_status": "degraded",
                "schema_reason": "missing schema_version",
            },
        ),
        (
            "not-a-snapshot",
            {
                "schema_label": DEGRADED_SNAPSHOT_SCHEMA_LABEL,
                "schema_status": "degraded",
                "schema_reason": "snapshot is not an object",
            },
        ),
    ],
)
def test_state_snapshot_schema_status_reports_schema_contract(snapshot, expected):
    assert state_snapshot_schema_status(snapshot) == expected


@pytest.mark.parametrize(
    ("snapshot", "expected"),
    [
        (None, None),
        ("not-a-snapshot", "degraded snapshot schema / snapshot is not an object"),
        ({}, "degraded snapshot schema / missing kind"),
        (
            {"kind": "supervisor_state_snapshot"},
            "supervisor_state_snapshot degraded / missing schema_version",
        ),
        (
            {"kind": "supervisor_state_snapshot", "schema_version": 1},
            "supervisor_state_snapshot v1",
        ),
    ],
)
def test_state_snapshot_schema_display_includes_degraded_reason(snapshot, expected):
    assert state_snapshot_schema_display(snapshot) == expected


@pytest.mark.parametrize(
    ("snapshot", "expected"),
    [
        (None, None),
        ("not-a-snapshot", None),
        ({}, DEGRADED_SNAPSHOT_SCHEMA_LABEL),
        (
            {"kind": "supervisor_state_snapshot"},
            "supervisor_state_snapshot degraded",
        ),
        (
            {"kind": "supervisor_state_snapshot", "schema_version": 1},
            "supervisor_state_snapshot v1",
        ),
    ],
)
def test_state_snapshot_schema_label_keeps_compact_label(snapshot, expected):
    assert state_snapshot_schema_label(snapshot) == expected
