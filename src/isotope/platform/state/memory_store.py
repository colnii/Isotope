"""Local memory record storage boundary."""

from __future__ import annotations

import json
from dataclasses import asdict
from json import JSONDecodeError
from pathlib import Path
from typing import Protocol

from ..schemas.memory import MemoryRecord


class MemoryStore(Protocol):
    """Persistence interface for structured memory records."""

    def append_record(self, record: MemoryRecord) -> MemoryRecord:
        """Append a new memory record."""

    def list_records(self, scope: str | None = None) -> list[MemoryRecord]:
        """List records, optionally filtered by memory scope."""

    def load_record(self, memory_id: str) -> MemoryRecord | None:
        """Load one record by id, or return None when it is absent."""


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
