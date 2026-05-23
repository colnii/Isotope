"""Small input-contract helpers shared by capacity and capability paths."""

from __future__ import annotations

from typing import Any, Literal, Mapping

ContractValueViolation = Literal["type", "enum"]


def matches_contract_type(value: Any, expected_type: str) -> bool:
    """Return whether a JSON-like value matches a top-level contract type."""

    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "object":
        return isinstance(value, Mapping)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "null":
        return value is None
    return True


def contract_value_violation(
    value: Any, schema: Mapping[str, Any]
) -> ContractValueViolation | None:
    """Return the first top-level contract violation kind for a value."""

    expected_type = schema.get("type")
    if isinstance(expected_type, str) and not matches_contract_type(
        value, expected_type
    ):
        return "type"
    enum_values = schema.get("enum")
    if isinstance(enum_values, list) and value not in enum_values:
        return "enum"
    return None


__all__ = [
    "ContractValueViolation",
    "contract_value_violation",
    "matches_contract_type",
]
