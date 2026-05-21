"""Not-enabled memory boundary for the Isotope v0.1 slice."""

from __future__ import annotations

from dataclasses import asdict
import json
import tempfile
from pathlib import Path
from typing import Any

from ..platform.schemas.memory import MemoryRecord


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


class FileMemoryStore:
    """Small local memory store for structured records."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def save_record(
        self,
        record: MemoryRecord | dict[str, Any],
        execution=None,
        grants: dict[str, Any] | None = None,
        event_store=None,
    ) -> dict[str, str]:
        if execution is None:
            raise PermissionError("memory persistence requires authorized execution")
        if not _has_write_memory_grant(grants):
            raise PermissionError("memory persistence requires write_memory grant")
        normalized = _normalize_memory_record(record)
        path = self.record_path(normalized.memory_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(normalized), sort_keys=True), encoding="utf-8")
        return {"status": "saved", "record_id": normalized.memory_id}

    def list_records(self, scope: str | None = None) -> list[MemoryRecord]:
        records: list[MemoryRecord] = []
        for path in sorted((self.root / "memory").glob("*.json")):
            try:
                record = MemoryRecord(**json.loads(path.read_text(encoding="utf-8")))
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                continue
            if scope is None or record.scope == scope:
                records.append(record)
        return records

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
            return {"status": "denied", "capability": "memory_query", "results": []}
        if controlled_expand and not _has_controlled_expand_grant(grants):
            return {"status": "denied", "capability": "memory_controlled_expand", "results": []}
        if not isinstance(query, str) or not query.strip():
            raise ValueError("memory query must be a non-empty string")
        if scope is not None and scope not in {"thread", "run", "session"}:
            raise ValueError("memory query scope must be thread, run, or session")

        needle = query.casefold()
        results = []
        for record in self.memory_store.list_records(scope=scope):
            if record.provenance.get("run_id") != run_id:
                continue
            searchable = f"{record.summary}\n{json.dumps(record.content, sort_keys=True)}".casefold()
            if needle not in searchable:
                continue
            results.append(
                {
                    "record_id": record.memory_id,
                    "scope": record.scope,
                    "summary": record.summary,
                    "source_refs": [dict(ref) for ref in record.source_refs],
                    "provenance": dict(record.provenance),
                    "quality": record.quality,
                }
            )
        return {"status": "ok", "capability": "memory_query", "results": results}


def _normalize_memory_record(record: MemoryRecord | dict[str, Any]) -> MemoryRecord:
    if isinstance(record, MemoryRecord):
        return record
    if not isinstance(record, dict):
        raise TypeError("memory record must be a MemoryRecord or dict")
    return MemoryRecord(**record)


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
            return {"status": "denied", "capability": "memory_query"}
        if controlled_expand and not _has_controlled_expand_grant(grants):
            return {"status": "denied", "capability": "memory_controlled_expand"}
        return {"status": "not_enabled", "capability": "memory_query", "results": []}


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
