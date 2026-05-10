"""Structured kernel errors for controlled helper and facade failures."""

from __future__ import annotations

from typing import Any


_CATEGORIES = {
    "validation",
    "not_found",
    "conflict",
    "not_enabled",
    "policy",
    "lifecycle",
    "internal",
}
_FORBIDDEN_DETAIL_KEYS = {
    "content",
    "full_content",
    "raw_content",
    "raw_payload",
    "raw_provider_payload",
    "secret",
    "token",
}


class KernelError(ValueError):
    """Controlled kernel error with stable metadata and ValueError compatibility."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        category: str,
        retryable: bool,
        http_status: int | None = None,
        details: dict[str, Any] | None = None,
    ):
        _validate_string("message", message)
        _validate_string("code", code)
        if not code.replace("_", "").isalnum() or code != code.lower():
            raise ValueError("code must be stable snake_case")
        if category not in _CATEGORIES:
            raise ValueError("category must be a known kernel error category")
        if not isinstance(retryable, bool):
            raise ValueError("retryable must be a bool")
        if http_status is not None and (not isinstance(http_status, int) or http_status < 100):
            raise ValueError("http_status must be an integer status code")
        safe_details = dict(details or {})
        _validate_details(safe_details)
        super().__init__(message)
        self.code = code
        self.category = category
        self.retryable = retryable
        self.http_status = http_status
        self.details = safe_details


def not_enabled_result(capability: str) -> dict[str, Any]:
    _validate_string("capability", capability)
    return {
        "status": "not_enabled",
        "capability": capability,
        "error": {
            "code": "not_enabled",
            "message": f"{capability} is not enabled",
            "category": "not_enabled",
            "retryable": False,
            "details": {"capability": capability},
            "capability": capability,
        },
    }


def _validate_string(field_name: str, value: object) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string")


def _validate_details(details: dict[str, Any]) -> None:
    for key, value in details.items():
        if key in _FORBIDDEN_DETAIL_KEYS:
            raise ValueError("details cannot include raw content, provider payloads, or secrets")
        if isinstance(value, (dict, list, tuple, set)):
            raise ValueError("details values must be low-sensitive scalar metadata")
