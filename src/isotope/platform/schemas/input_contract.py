"""Small input-contract helpers shared by capacity and capability paths."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal, Mapping

ContractValueViolation = Literal["type", "enum"]


def contract_properties(input_contract: Any) -> Mapping[str, Any]:
    """Return contract properties when they are mapping-shaped."""

    if not isinstance(input_contract, Mapping):
        return {}
    properties = input_contract.get("properties", {})
    if not isinstance(properties, Mapping):
        return {}
    return properties


def public_contract_properties(input_contract: Any) -> dict[str, Any]:
    """Return properties that are safe to show to users and models."""

    properties = contract_properties(input_contract)
    return {
        name: schema
        for name, schema in properties.items()
        if isinstance(schema, Mapping) and schema.get("x-system-input") is not True
    }


def system_contract_keys(input_contract: Any) -> list[str]:
    """Return input keys supplied by Isotope rather than users or models."""

    properties = contract_properties(input_contract)
    return [
        name
        for name, schema in properties.items()
        if isinstance(schema, Mapping) and schema.get("x-system-input") is True
    ]


def public_required_contract_keys(input_contract: Any) -> list[str]:
    """Return required keys after removing system-supplied inputs."""

    system_keys = set(system_contract_keys(input_contract))
    return [
        key
        for key in required_contract_keys(input_contract)
        if key not in system_keys
    ]


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


def required_contract_keys(input_contract: Any) -> list[str]:
    """Return string required keys from a contract in declaration order."""

    if not isinstance(input_contract, Mapping):
        return []
    required = input_contract.get("required", [])
    if not isinstance(required, list):
        return []
    return [name for name in required if isinstance(name, str)]


def missing_required_input_keys(
    values: Mapping[str, Any] | None, required_keys: Sequence[str]
) -> list[str]:
    """Return required keys absent from input values."""

    input_mapping = values or {}
    return [
        name
        for name in required_keys
        if name not in input_mapping or input_mapping.get(name) in (None, "")
    ]


__all__ = [
    "ContractValueViolation",
    "contract_properties",
    "contract_value_violation",
    "duplicate_required_contract_keys",
    "matches_contract_type",
    "missing_required_input_keys",
    "public_contract_properties",
    "public_required_contract_keys",
    "required_contract_keys",
    "system_contract_keys",
    "undeclared_required_contract_keys",
    "unexpected_contract_keys",
]
