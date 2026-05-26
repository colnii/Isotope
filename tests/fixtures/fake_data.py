"""Generic fake data factories for test objects.

Keeps test files from repeating the same minimal-object construction.
"""

from pathlib import Path
from typing import Any


def sample_event(
    event_id: str = "evt_001",
    run_id: str = "run_001",
    event_type: str = "action.proposed",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a minimal event dict."""
    return {
        "event_id": event_id,
        "run_id": run_id,
        "event_type": event_type,
        "payload": payload or {"proposal_id": "prop_001"},
        "created_at": "2026-04-27T00:00:00Z",
    }
