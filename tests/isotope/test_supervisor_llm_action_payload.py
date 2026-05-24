from __future__ import annotations

import pytest

from isotope.features.supervisor.llm_action_payload import (
    extract_json_object,
    normalize_llm_action_payload,
    optional_payload_string,
    required_payload_bool,
    required_payload_string,
)


def test_llm_action_payload_extracts_noisy_json_and_normalizes_action_alias():
    payload = extract_json_object('notes before {"action": "monitor", "reason": "ok"}')

    assert normalize_llm_action_payload(payload) == {
        "action": "monitor",
        "kind": "monitor",
        "reason": "ok",
    }


def test_llm_action_payload_validates_required_fields():
    payload = {"kind": "ask_user", "question": "  继续吗  ", "confirmed": True}

    assert required_payload_string(payload, "question") == "继续吗"
    assert optional_payload_string(payload, "missing") is None
    assert required_payload_bool(payload, "confirmed") is True

    with pytest.raises(ValueError, match="LLM action field is required: session_id"):
        required_payload_string(payload, "session_id")
