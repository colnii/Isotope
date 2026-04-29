"""Not-enabled memory boundary for the Isotope v0.1 slice."""

from __future__ import annotations


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
