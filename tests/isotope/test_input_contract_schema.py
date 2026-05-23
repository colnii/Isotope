from __future__ import annotations

import pytest

from isotope.platform.schemas.input_contract import matches_contract_type


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
