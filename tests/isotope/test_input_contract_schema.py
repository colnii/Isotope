from __future__ import annotations

import pytest

from isotope.platform.schemas.input_contract import (
    contract_properties,
    contract_value_violation,
    duplicate_required_contract_keys,
    matches_contract_type,
    missing_required_input_keys,
    required_contract_keys,
    undeclared_required_contract_keys,
    unexpected_contract_keys,
)


@pytest.mark.parametrize(
    ("value", "expected_type"),
    [
        ("summary", "string"),
        (5, "integer"),
        (5, "number"),
        (5.5, "number"),
        (True, "boolean"),
        ({"query": "capacity"}, "object"),
        (["summary"], "array"),
        (None, "null"),
    ],
)
def test_matches_contract_type_accepts_supported_json_like_types(value, expected_type):
    assert matches_contract_type(value, expected_type) is True


@pytest.mark.parametrize(
    ("value", "expected_type"),
    [
        (True, "integer"),
        (False, "number"),
        ("5", "integer"),
        (5, "string"),
        ({"items": []}, "array"),
        (["query"], "object"),
        ("", "null"),
    ],
)
def test_matches_contract_type_rejects_mismatched_json_like_types(value, expected_type):
    assert matches_contract_type(value, expected_type) is False


def test_matches_contract_type_allows_unknown_contract_type_for_forward_compatibility():
    assert matches_contract_type("anything", "future-type") is True


def test_contract_value_violation_reports_type_mismatch_before_enum():
    violation = contract_value_violation(
        "summary",
        {"type": "integer", "enum": ["summary"]},
    )

    assert violation == "type"


def test_contract_value_violation_reports_enum_mismatch_after_type_match():
    violation = contract_value_violation(
        "raw",
        {"type": "string", "enum": ["summary", "detail"]},
    )

    assert violation == "enum"


def test_contract_value_violation_accepts_values_without_type_or_enum_mismatch():
    assert contract_value_violation("summary", {"type": "string"}) is None
    assert contract_value_violation("anything", {"type": "future-type"}) is None
    assert contract_value_violation("anything", {}) is None


def test_contract_properties_returns_property_schemas():
    properties = contract_properties(
        {
            "properties": {
                "query": {"type": "string"},
                "mode": {"type": "string", "enum": ["summary"]},
            }
        }
    )

    assert properties == {
        "query": {"type": "string"},
        "mode": {"type": "string", "enum": ["summary"]},
    }


def test_contract_properties_returns_empty_for_malformed_contract_shapes():
    assert contract_properties(None) == {}
    assert contract_properties({"properties": ["query"]}) == {}
    assert contract_properties({}) == {}


def test_unexpected_contract_keys_reports_inputs_outside_properties():
    unexpected = unexpected_contract_keys(
        {"query": "capacity", "raw_content": "...", "mode": "summary"},
        {
            "query": {"type": "string"},
            "mode": {"type": "string"},
        },
    )

    assert unexpected == ["raw_content"]


def test_unexpected_contract_keys_returns_empty_for_declared_inputs():
    unexpected = unexpected_contract_keys(
        {"query": "capacity"},
        {"query": {"type": "string"}},
    )

    assert unexpected == []


def test_duplicate_required_contract_keys_reports_unique_sorted_duplicates():
    duplicates = duplicate_required_contract_keys(
        {
            "required": ["question", "artifact_ref", "question", "artifact_ref"],
            "properties": {
                "artifact_ref": {"type": "string"},
                "question": {"type": "string"},
            },
        }
    )

    assert duplicates == ["artifact_ref", "question"]


def test_undeclared_required_contract_keys_reports_required_missing_from_properties():
    missing = undeclared_required_contract_keys(
        {
            "required": ["artifact_ref", "question", "raw_content"],
            "properties": {
                "artifact_ref": {"type": "string"},
                "question": {"type": "string"},
            },
        }
    )

    assert missing == ["raw_content"]


def test_required_contract_key_helpers_ignore_malformed_contract_shapes():
    assert duplicate_required_contract_keys({"required": "question"}) == []
    assert duplicate_required_contract_keys({"required": ["question", 5, 5]}) == []
    assert undeclared_required_contract_keys({"required": "question"}) == []
    assert undeclared_required_contract_keys(
        {
            "required": ["question", 5],
            "properties": {"question": {"type": "string"}},
        }
    ) == []
    assert undeclared_required_contract_keys(
        {"required": ["question"], "properties": ["question"]}
    ) == []


def test_undeclared_required_contract_keys_treats_missing_properties_as_empty():
    missing = undeclared_required_contract_keys({"required": ["question"]})

    assert missing == ["question"]


def test_required_contract_keys_returns_string_required_fields_in_order():
    required = required_contract_keys(
        {
            "required": ["artifact_ref", "question", 5],
            "properties": {
                "artifact_ref": {"type": "string"},
                "question": {"type": "string"},
            },
        }
    )

    assert required == ["artifact_ref", "question"]


def test_required_contract_keys_ignores_malformed_required_shape():
    assert required_contract_keys({"required": "question"}) == []


def test_missing_required_input_keys_reports_absent_none_and_empty_values():
    missing = missing_required_input_keys(
        {"artifact_ref": "artifact://1", "question": "", "count": 0, "enabled": False},
        ["artifact_ref", "question", "cwd", "count", "enabled", "note"],
    )

    assert missing == ["question", "cwd", "note"]


def test_missing_required_input_keys_treats_none_inputs_as_empty():
    missing = missing_required_input_keys(None, ["query", "cwd"])

    assert missing == ["query", "cwd"]
