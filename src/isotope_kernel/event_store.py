"""File event store boundary for the Isotope v0.1 slice."""

from __future__ import annotations

import json
from pathlib import Path

from .events import CanonicalEvent


class FileEventStore:
    """Append-only JSONL event store for the first vertical slice."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def event_path(self, run_id: str) -> Path:
        return self.root / "runs" / run_id / "events.jsonl"

    def append(self, event: CanonicalEvent) -> CanonicalEvent:
        path = self.event_path(event.run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.to_dict(), sort_keys=True) + "\n")
        return event

    def list_events(self, run_id: str) -> list[CanonicalEvent]:
        path = self.event_path(run_id)
        if not path.exists():
            return []
        events = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(CanonicalEvent.from_dict(json.loads(line)))
        return events
