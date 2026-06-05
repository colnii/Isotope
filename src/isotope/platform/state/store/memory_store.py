"""Local memory record storage boundary."""

from __future__ import annotations

import json
from dataclasses import asdict
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Protocol

from ...schemas.memory import MemoryRecord


def _has_write_memory_grant(grants: dict[str, Any] | None) -> bool:
    if not isinstance(grants, dict):
        return False
    tools = grants.get("tools")
    return isinstance(tools, list) and "write_memory" in tools


def _normalize_memory_record(record: MemoryRecord | dict[str, Any]) -> MemoryRecord:
    if isinstance(record, MemoryRecord):
        return record
    if not isinstance(record, dict):
        raise TypeError("memory record must be a MemoryRecord or dict")
    return MemoryRecord(**record)


class MemoryStore(Protocol):
    """Persistence interface for structured memory records."""

    def append_record(self, record: MemoryRecord) -> MemoryRecord:
        """Append a new memory record."""

    def list_records(self, scope: str | None = None) -> list[MemoryRecord]:
        """List records, optionally filtered by memory scope."""

    def load_record(self, memory_id: str) -> MemoryRecord | None:
        """Load one record by id, or return None when it is absent."""


class FileMemoryStore:
    """One-file-per-record implementation for local structured memory records."""

    VALID_SCOPES = {"thread", "run", "session"}

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
        self.append_record(normalized)
        return {"status": "saved", "record_id": normalized.memory_id}

    def append_record(self, record: MemoryRecord) -> MemoryRecord:
        if not isinstance(record, MemoryRecord):
            raise TypeError("FileMemoryStore.append_record requires a MemoryRecord")

        path = self.record_path(record.memory_id)
        if path.exists():
            raise ValueError(f"duplicate memory_id in memory store: {record.memory_id}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(record), sort_keys=True), encoding="utf-8")
        return record

    def list_records(self, scope: str | None = None) -> list[MemoryRecord]:
        if scope is not None and scope not in self.VALID_SCOPES:
            raise ValueError("scope must be one of thread, run, session")

        records: list[MemoryRecord] = []
        for path in sorted((self.root / "memory").glob("*.json")):
            try:
                record = MemoryRecord(**json.loads(path.read_text(encoding="utf-8")))
            except (OSError, TypeError, ValueError, JSONDecodeError):
                continue
            if scope is None or record.scope == scope:
                records.append(record)
        return records

    def load_record(self, memory_id: str) -> MemoryRecord | None:
        path = self.record_path(memory_id)
        if not path.exists():
            return None
        try:
            return MemoryRecord(**json.loads(path.read_text(encoding="utf-8")))
        except (OSError, TypeError, ValueError, JSONDecodeError):
            return None

    def record_path(self, memory_id: str) -> Path:
        return self.root / "memory" / f"{memory_id}.json"


class JsonlMemoryStore:
    """Append-only JSONL implementation for local structured memory records."""

    VALID_SCOPES = {"thread", "run", "session"}

    def __init__(self, root: Path):
        self.root = Path(root)

    def records_path(self) -> Path:
        return self.root / "memory" / "records.jsonl"

    def append_record(self, record: MemoryRecord) -> MemoryRecord:
        if not isinstance(record, MemoryRecord):
            raise TypeError("JsonlMemoryStore.append_record requires a MemoryRecord")

        if self.load_record(record.memory_id) is not None:
            raise ValueError(f"duplicate memory_id in memory store: {record.memory_id}")

        path = self.records_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(record), sort_keys=True) + "\n")
        return record

    def list_records(self, scope: str | None = None) -> list[MemoryRecord]:
        if scope is not None and scope not in self.VALID_SCOPES:
            raise ValueError("scope must be one of thread, run, session")

        path = self.records_path()
        if not path.exists():
            return []

        records: list[MemoryRecord] = []
        lines = path.read_text(encoding="utf-8").splitlines()
        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except JSONDecodeError as exc:
                raise ValueError(
                    f"malformed JSON in memory store at line {line_number}"
                ) from exc
            try:
                record = MemoryRecord(**data)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"malformed memory record in memory store at line {line_number}"
                ) from exc
            if scope is None or record.scope == scope:
                records.append(record)
        return records

    def load_record(self, memory_id: str) -> MemoryRecord | None:
        for record in self.list_records():
            if record.memory_id == memory_id:
                return record
        return None
