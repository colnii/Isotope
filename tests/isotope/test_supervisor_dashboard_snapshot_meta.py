from __future__ import annotations

import pytest

from isotope.features.supervisor.commands.dashboard import dashboard_state_snapshot_meta
from isotope.features.supervisor.commands.snapshot_display import (
    DEGRADED_SNAPSHOT_SCHEMA_LABEL,
    STATE_SNAPSHOT_SOURCE_LABEL,
)


@pytest.mark.parametrize(
    ("snapshot", "expected"),
    [
        (
            {
                "status": "ok",
                "kind": "supervisor_state_snapshot",
                "schema_version": 1,
            },
            {
                "kind": "supervisor_state_snapshot",
                "schema_version": 1,
                "schema_label": "supervisor_state_snapshot v1",
                "schema_status": "ok",
                "schema_reason": None,
                "source_label": STATE_SNAPSHOT_SOURCE_LABEL,
            },
        ),
        (
            {"status": "ok", "schema_version": 1},
            {
                "kind": None,
                "schema_version": 1,
                "schema_label": DEGRADED_SNAPSHOT_SCHEMA_LABEL,
                "schema_status": "degraded",
                "schema_reason": "missing kind",
                "source_label": STATE_SNAPSHOT_SOURCE_LABEL,
            },
        ),
        (
            {"status": "ok", "kind": "supervisor_state_snapshot"},
            {
                "kind": "supervisor_state_snapshot",
                "schema_version": None,
                "schema_label": "supervisor_state_snapshot degraded",
                "schema_status": "degraded",
                "schema_reason": "missing schema_version",
                "source_label": STATE_SNAPSHOT_SOURCE_LABEL,
            },
        ),
    ],
)
def test_dashboard_state_snapshot_meta_reports_schema_status(snapshot, expected):
    assert dashboard_state_snapshot_meta(snapshot) == expected
