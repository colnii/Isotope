"""Supervisor adapter for the reusable failure ledger."""

from __future__ import annotations

from pathlib import Path

from isotope.platform.state.failure_ledger import FailureLedger


def default_failure_ledger_path(codex_home: Path | str) -> Path:
    return Path(codex_home).expanduser() / "supervisor" / "failure_events.jsonl"


__all__ = ["FailureLedger", "default_failure_ledger_path"]
