"""File event store boundary for the Isotope v0.1 slice."""

from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path

from ..events.events import CanonicalEvent


class FileEventStore:
    """Append-only JSONL event store for the first vertical slice."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def event_path(self, run_id: str) -> Path:
        return self.root / "runs" / run_id / "events.jsonl"

    def append(self, event: CanonicalEvent, run_id: str | None = None) -> CanonicalEvent:
        if not isinstance(event, CanonicalEvent):
            raise TypeError("FileEventStore.append requires a CanonicalEvent")

        target_run_id = event.run_id if run_id is None else run_id
        if target_run_id != event.run_id:
            raise ValueError("run_id mismatch between target path and event")

        for existing in self.list_events(target_run_id):
            if existing.event_id == event.event_id:
                raise ValueError(f"duplicate event_id in run {target_run_id}: {event.event_id}")

        path = self.event_path(target_run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.to_dict(), sort_keys=True) + "\n")
        return event

    def list_events(self, run_id: str) -> list[CanonicalEvent]:
        path = self.event_path(run_id)
        if not path.exists():
            return []
        events = []
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if line.strip():
                try:
                    data = json.loads(line)
                except JSONDecodeError as exc:
                    raise ValueError(
                        f"malformed JSON in event log for run {run_id} at line {line_number}"
                    ) from exc
                events.append(CanonicalEvent.from_dict(data))
        return events
