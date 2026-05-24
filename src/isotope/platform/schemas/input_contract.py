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


def unexpected_contract_keys(
    values: Mapping[str, Any], properties: Mapping[str, Any]
) -> list[str]:
    """Return input keys not declared in contract properties."""

    allowed = {name for name in properties if isinstance(name, str)}
    return sorted(name for name in values if name not in allowed)


def duplicate_required_contract_keys(input_contract: Mapping[str, Any]) -> list[str]:
    """Return required keys that appear more than once."""

    required = input_contract.get("required", [])
    if not isinstance(required, list):
        return []
    required_names = [name for name in required if isinstance(name, str)]
    return sorted(
        {name for name in required_names if required_names.count(name) > 1}
    )


def undeclared_required_contract_keys(input_contract: Mapping[str, Any]) -> list[str]:
    """Return required keys not declared in contract properties."""

    required = input_contract.get("required", [])
    properties = input_contract.get("properties", {})
    if not isinstance(required, list) or not isinstance(properties, Mapping):
        return []
    return sorted(
        name for name in required if isinstance(name, str) and name not in properties
    )


__all__ = [
    "ContractValueViolation",
    "contract_value_violation",
    "duplicate_required_contract_keys",
    "matches_contract_type",
    "undeclared_required_contract_keys",
    "unexpected_contract_keys",
]
