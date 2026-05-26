"""Shared HTTP response types for the in-process API facade."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HttpResponse:
    """Small response shape for in-process API tests."""

    status_code: int
    body: dict[str, Any] | list[dict[str, Any]]

    def json(self) -> dict[str, Any] | list[dict[str, Any]]:
        return self.body
