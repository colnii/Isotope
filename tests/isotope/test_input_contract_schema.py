from __future__ import annotations

import pytest

from isotope.platform.schemas.input_contract import (
    contract_value_violation,
    duplicate_required_contract_keys,
    matches_contract_type,
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
