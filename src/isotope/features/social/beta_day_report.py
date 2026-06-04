"""Build QQ beta day reports from operator review artifacts."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class QQBetaDayReportConfig:
    date: str
    group_id: str
    dry_run_review: Path
    export_log: Path
    failures_json: Path | None
    output: Path

    def __post_init__(self) -> None:
        _required_text(self.date, "date")
        _required_text(self.group_id, "group")
        _required_path(self.dry_run_review, "dry-run-review")
        _required_path(self.export_log, "export-log")
        if self.failures_json is not None:
            _required_path(self.failures_json, "failures-json")
        _required_path(self.output, "output")


def build_qq_beta_day_report(config: QQBetaDayReportConfig) -> dict[str, Any]:
    review = _read_json_object(config.dry_run_review)
    export_log = _read_json_object(config.export_log)
    failures_payload = (
        _read_json_object(config.failures_json)
        if config.failures_json is not None
        else {"failures": []}
    )

    review_summary = _dict_value(review, "summary")
    review_warnings = _list_value(review, "warnings")
    entries = _list_value(export_log, "entries")
    failures = _failure_entries(failures_payload)
    audit_counts = _audit_counts(entries, group_id=config.group_id)
    open_failures = [
        failure
        for failure in failures
        if str(failure.get("status", "open")).strip().lower()
        not in {"closed", "resolved", "fixed"}
    ]
    ready_for_send = (
        bool(review.get("ready_for_send"))
        and not review_warnings
        and not open_failures
    )
    summary = {
        **review_summary,
        "audit_entry_count": sum(audit_counts.values()),
        "audit_counts": dict(audit_counts),
        "failure_count": len(failures),
        "open_failure_count": len(open_failures),
        "warning_count": len(review_warnings),
    }
    next_actions = _next_actions(
        ready_for_send=ready_for_send,
        open_failure_count=len(open_failures),
        warning_count=len(review_warnings),
    )
    return {
        "kind": "qq_beta_day_report",
        "date": config.date,
        "group_id": config.group_id,
        "ready_for_send": ready_for_send,
        "inputs": {
            "dry_run_review": str(config.dry_run_review),
            "export_log": str(config.export_log),
            "failures_json": str(config.failures_json) if config.failures_json else None,
        },
        "summary": summary,
        "review_warnings": review_warnings,
        "failures": failures,
        "next_actions": next_actions,
    }


def write_qq_beta_day_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _audit_counts(entries: list[Any], *, group_id: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("export-log entries must contain JSON objects")
        entry_group = entry.get("group_id")
        if entry_group is not None and str(entry_group) != group_id:
            continue
        kind = entry.get("kind")
        if not isinstance(kind, str) or not kind.strip():
            raise ValueError("export-log entry kind must be a non-empty string")
        counts[kind] += 1
    return Counter(dict(sorted(counts.items())))


def _next_actions(
    *,
    ready_for_send: bool,
    open_failure_count: int,
    warning_count: int,
) -> list[str]:
    actions: list[str] = []
    if open_failure_count:
        actions.append("resolve_open_failures")
    if warning_count:
        actions.append("review_dry_run_warnings")
    if not ready_for_send:
        actions.append("keep_send_guarded")
    if ready_for_send:
        actions.append("operator_review_before_send")
    return actions


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _dict_value(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be a JSON object")
    return dict(value)


def _list_value(payload: dict[str, Any], key: str) -> list[Any]:
    value = payload.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a JSON array")
    return list(value)


def _failure_entries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    failures = _list_value(payload, "failures")
    result: list[dict[str, Any]] = []
    for failure in failures:
        if not isinstance(failure, dict):
            raise ValueError("failures must contain JSON objects")
        result.append(dict(failure))
    return result


def _required_text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _required_path(path: Path, name: str) -> None:
    if not str(path).strip():
        raise ValueError(f"{name} must be a non-empty path")
