"""Not-enabled memory boundary for the Isotope v0.1 slice."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from .models import MemoryRecord


def _has_write_memory_grant(grants: dict[str, Any] | None) -> bool:
    if not isinstance(grants, dict):
        return False
    tools = grants.get("tools")
    return isinstance(tools, list) and "write_memory" in tools


def _validate_memory_record_shape(record: MemoryRecord | dict[str, Any]) -> None:
    if isinstance(record, MemoryRecord):
        return
    if not isinstance(record, dict):
        raise TypeError("memory record must be a MemoryRecord or dict")
    if not isinstance(record.get("content"), dict):
        raise ValueError("memory record content must be a structured dict")
    if not isinstance(record.get("source_refs"), list):
        raise ValueError("memory record source_refs must be a list")
    provenance = record.get("provenance")
    if not isinstance(provenance, dict):
        raise ValueError("memory record provenance must be a dict")
    for field_name in ("run_id", "execution_id", "action_type"):
        value = provenance.get(field_name)
        if not isinstance(value, str) or not value:
            raise ValueError(f"memory record provenance.{field_name} must be a non-empty string")


class NotEnabledMemoryStore:
    """Not-enabled persistence boundary; it never writes durable records."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = (
            Path(root)
            if root is not None
            else Path(tempfile.gettempdir()) / "isotope-not-enabled-memory"
        )

    def save_record(
        self,
        record: MemoryRecord | dict[str, Any],
        execution=None,
        grants: dict[str, Any] | None = None,
        event_store=None,
    ) -> dict[str, str]:
        if execution is None:
            raise PermissionError("memory persistence requires authorized execution; not enabled")
        if not _has_write_memory_grant(grants):
            raise PermissionError("memory persistence requires write_memory grant; not enabled")
        _validate_memory_record_shape(record)
        raise PermissionError("memory persistence not enabled for memory_record")

    def list_records(self, scope: str | None = None) -> list[MemoryRecord]:
        return []

    def record_path(self, memory_id: str) -> Path:
        return self.root / "memory" / f"{memory_id}.json"


class NotEnabledMemoryService:
    """Deferred memory query boundary for the v0.1 slice."""

    def write_record(
        self,
        record: dict,
        execution=None,
        grants: dict | None = None,
    ) -> dict[str, str]:
        raise PermissionError("memory_write not enabled without authorized execution")

    def query(
        self,
        run_id: str,
        query: str,
        grants: dict | None = None,
        caller_context: dict | None = None,
    ) -> dict[str, str]:
        return {"status": "not_enabled", "capability": "memory_query"}
