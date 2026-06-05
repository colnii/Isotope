from __future__ import annotations

from isotope.features.supervisor.commands.supervisor_action import (
    supervisor_action_from_payload,
)


def test_supervisor_action_from_payload_prefers_neutral_alias() -> None:
    payload = {
        "llm_action": {"kind": "monitor", "reason": "legacy"},
        "supervisor_action": {"kind": "send_status", "reason": "neutral"},
    }

    assert supervisor_action_from_payload(payload) == {
        "kind": "send_status",
        "reason": "neutral",
    }


def test_supervisor_action_from_payload_falls_back_to_legacy_llm_action() -> None:
    payload = {"llm_action": {"kind": "monitor", "reason": "legacy"}}

    assert supervisor_action_from_payload(payload) == {
        "kind": "monitor",
        "reason": "legacy",
    }
