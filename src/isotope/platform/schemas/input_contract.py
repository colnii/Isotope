"""Small input-contract helpers shared by capacity and capability paths."""

from __future__ import annotations

from typing import Any, Mapping


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


__all__ = ["matches_contract_type"]
