"""Global test configuration and shared fixtures.

Keep this file lean — only genuinely cross-cutting fixtures live here.
Module-level or domain-specific fixtures belong in tests/fixtures/.
"""

from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest


# ── shared helpers ──────────────────────────────────────────────────────
# These are not fixtures — they are exposed as plain Python so sub-agent
# sessions and helper modules can import them without depending on pytest.


def make_memory_record(
    memory_id: str = "mem_001",
    scope: str = "thread",
    content: dict[str, Any] | None = None,
    summary: str | None = None,
    run_id: str = "run_001",
    execution_id: str = "exec_001",
) -> dict[str, Any]:
    """Return a minimal memory-record dict suitable for most unit tests.

    The caller can decide whether to construct the record as a plain dict
    or pass it to a MemoryRecord dataclass.  This keeps the helper decoupled
    from any single schema definition.
    """
    return {
        "memory_id": memory_id,
        "scope": scope,
        "content": content or {
            "kind": "structured_note",
            "text": f"{memory_id} prefers worked examples.",
        },
        "summary": summary or f"{memory_id} prefers worked examples.",
        "source_refs": [
            {
                "ref_type": "artifact",
                "run_id": run_id,
                "artifact_id": f"artifact_{memory_id}",
            }
        ],
        "provenance": {
            "run_id": run_id,
            "execution_id": execution_id,
            "action_type": "write_memory",
        },
        "created_at": "2026-04-29T00:00:00Z",
        "supersedes": [],
        "quality": "candidate",
    }
