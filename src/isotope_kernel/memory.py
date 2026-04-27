"""Not-enabled memory boundary for the Isotope v0.1 slice."""

from __future__ import annotations


class NotEnabledMemoryService:
    """Deferred memory query boundary for the v0.1 slice."""

    def query(self, run_id: str, query: str) -> dict[str, str]:
        return {"status": "not_enabled", "capability": "memory_query"}
