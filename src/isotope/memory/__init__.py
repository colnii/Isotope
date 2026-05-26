"""Not-enabled memory boundary for the Isotope v0.1 slice."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from ..platform.schemas.memory import MemoryRecord
from ..platform.state.memory_store import FileMemoryStore
from .views import query_memory_records


def _has_write_memory_grant(grants: dict[str, Any] | None) -> bool:
    if not isinstance(grants, dict):
        return False
    tools = grants.get("tools")
    return isinstance(tools, list) and "write_memory" in tools


def _memory_grants(grants: dict[str, Any]) -> dict[str, Any]:
    memory_grants = grants.get("memory")
    return memory_grants if isinstance(memory_grants, dict) else {}


def _has_memory_query_grant(grants: dict[str, Any]) -> bool:
    return _memory_grants(grants).get("query") is True


def _has_controlled_expand_grant(grants: dict[str, Any]) -> bool:
    memory_grants = _memory_grants(grants)
    return memory_grants.get("controlled_expand") is True and (
        "expand_budget" in memory_grants or "budget" in memory_grants
    )


def _denied_memory_query_result(
    *,
    capability: str,
    reason_code: str,
    content_policy: str,
) -> dict[str, Any]:
    return {
        "status": "denied",
        "capability": capability,
        "reason_code": reason_code,
        "content_policy": content_policy,
        "results": [],
    }


def _not_enabled_memory_query_result() -> dict[str, Any]:
    return {
        "status": "not_enabled",
        "capability": "memory_query",
        "reason_code": "memory_query_not_enabled",
        "content_policy": "summary_refs_provenance_only",
        "results": [],
    }


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


class LocalMemoryQueryService:
    """Query local memory records and return previews only by default."""

    def __init__(self, memory_store: FileMemoryStore) -> None:
        self.memory_store = memory_store

    def query(
        self,
        run_id: str,
        query: str,
        grants: dict[str, Any] | None = None,
        caller_context: dict[str, Any] | None = None,
        controlled_expand: bool = False,
        scope: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(grants, dict):
            raise ValueError("memory_query grants must be provided as a dict")
        if not isinstance(caller_context, dict):
            raise ValueError("memory_query caller_context must be provided as a dict")
        if not _has_memory_query_grant(grants):
            return _denied_memory_query_result(
                capability="memory_query",
                reason_code="missing_memory_query_grant",
                content_policy="no_memory_read",
            )
        if controlled_expand and not _has_controlled_expand_grant(grants):
            return _denied_memory_query_result(
                capability="memory_controlled_expand",
                reason_code="missing_controlled_expand_grant",
                content_policy="no_full_content_read",
            )
        if not isinstance(query, str) or not query.strip():
            raise ValueError("memory query must be a non-empty string")
        if scope is not None and scope not in {"thread", "run", "session"}:
            raise ValueError("memory query scope must be thread, run, or session")

        matches = query_memory_records(
            self.memory_store.list_records(scope=scope),
            query=query,
            run_id=run_id,
        )
        results = [
            {
                "record_id": record.memory_id,
                "scope": record.scope,
                "summary": record.summary,
                "source_refs": [dict(ref) for ref in record.source_refs],
                "provenance": dict(record.provenance),
                "quality": record.quality,
            }
            for record in matches.visible
        ]
        return {
            "status": "ok",
            "capability": "memory_query",
            "content_policy": "summary_refs_provenance_only",
            "results": results,
        }


class NotEnabledMemoryQueryService:
    """Not-enabled query boundary; it validates auth shape before refusing."""

    def __init__(self, memory_store=None) -> None:
        self.memory_store = memory_store

    def query(
        self,
        run_id: str,
        query: str,
        grants: dict[str, Any] | None = None,
        caller_context: dict[str, Any] | None = None,
        controlled_expand: bool = False,
    ) -> dict[str, Any]:
        if not isinstance(grants, dict):
            raise ValueError("memory_query grants must be provided as a dict")
        if not isinstance(caller_context, dict):
            raise ValueError("memory_query caller_context must be provided as a dict")
        if not _has_memory_query_grant(grants):
            return _denied_memory_query_result(
                capability="memory_query",
                reason_code="missing_memory_query_grant",
                content_policy="no_memory_read",
            )
        if controlled_expand and not _has_controlled_expand_grant(grants):
            return _denied_memory_query_result(
                capability="memory_controlled_expand",
                reason_code="missing_controlled_expand_grant",
                content_policy="no_full_content_read",
            )
        return _not_enabled_memory_query_result()


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
