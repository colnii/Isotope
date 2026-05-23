"""Read-only Supervisor view over local memory records."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from isotope.platform.schemas.memory import MemoryRecord
from isotope.platform.state.memory_store import FileMemoryStore


VALID_SCOPES = ("thread", "run", "session")


def build_memory_status_payload(
    *,
    root: Path | str,
    scope: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    root_path = Path(root).expanduser()
    if scope is not None and scope not in VALID_SCOPES:
        raise ValueError("memory scope must be thread, run, or session")
    if limit <= 0:
        raise ValueError("limit must be positive")

    records = FileMemoryStore(root_path).list_records(scope=scope)
    sorted_records = sorted(
        records,
        key=lambda record: (record.created_at, record.memory_id),
        reverse=True,
    )
    visible = sorted_records[:limit]
    by_scope = Counter(record.scope for record in records)
    by_quality = Counter(record.quality for record in records)
    return {
        "status": "ok",
        "store": {
            "root": str(root_path),
            "path": str(root_path / "memory"),
            "format": "file_memory_store",
        },
        "scope": scope,
        "summary": {
            "total": len(records),
            "by_scope": {scope_name: by_scope.get(scope_name, 0) for scope_name in VALID_SCOPES},
            "by_quality": dict(sorted(by_quality.items())),
            "hidden_records": max(0, len(records) - len(visible)),
        },
        "records": [_memory_record_preview(record) for record in visible],
    }


def render_memory_status_plain(payload: dict[str, Any]) -> str:
    store = payload.get("store") if isinstance(payload.get("store"), dict) else {}
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    records = payload.get("records") if isinstance(payload.get("records"), list) else []
    lines = [
        "Memory store",
        f"root: {store.get('root', '')}",
        f"path: {store.get('path', '')}",
        f"total: {summary.get('total', 0)}",
    ]
    by_scope = summary.get("by_scope")
    if isinstance(by_scope, dict):
        lines.append(
            "scope: "
            + " / ".join(f"{scope}={by_scope.get(scope, 0)}" for scope in VALID_SCOPES)
        )
    by_quality = summary.get("by_quality")
    if isinstance(by_quality, dict) and by_quality:
        lines.append(
            "quality: "
            + " / ".join(f"{key}={value}" for key, value in sorted(by_quality.items()))
        )
    if summary.get("hidden_records"):
        lines.append(f"hidden_records: {summary['hidden_records']}")
    if records:
        lines.append("records:")
        for record in records:
            lines.append(
                "- {record_id} / {scope} / {quality} / {summary}".format(
                    record_id=record.get("record_id", "unknown"),
                    scope=record.get("scope", "unknown"),
                    quality=record.get("quality", "unknown"),
                    summary=record.get("summary", ""),
                )
            )
    else:
        lines.append("records: none")
    return "\n".join(lines)


def _memory_record_preview(record: MemoryRecord) -> dict[str, Any]:
    return {
        "record_id": record.memory_id,
        "scope": record.scope,
        "summary": record.summary,
        "source_refs": [dict(ref) for ref in record.source_refs],
        "provenance": dict(record.provenance),
        "created_at": record.created_at,
        "supersedes": list(record.supersedes),
        "quality": record.quality,
    }
