"""Append structured QQ beta failure records."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class QQRecordFailureConfig:
    failures_json: Path
    date: str
    group_id: str
    symptom: str
    status: str = "open"
    observed_input: str = ""
    decision_log_entry: str = ""
    send_or_capability_log_entry: str = ""
    root_cause: str = ""
    fix: str = ""
    regression_test: str = ""

    def __post_init__(self) -> None:
        if not str(self.failures_json).strip():
            raise ValueError("failures-json must be a non-empty path")
        _required_text(self.date, "date")
        _required_text(self.group_id, "group")
        _required_text(self.symptom, "symptom")
        _required_text(self.status, "status")


def record_qq_beta_failure(config: QQRecordFailureConfig) -> dict[str, Any]:
    payload = _read_failures(config.failures_json)
    failures = payload["failures"]
    failure = _failure_payload(config)
    failures.append(failure)
    config.failures_json.parent.mkdir(parents=True, exist_ok=True)
    config.failures_json.write_text(
        json.dumps({"failures": failures}, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return {
        "failures_json": str(config.failures_json),
        "failure_count": len(failures),
        "failure": failure,
    }


def _read_failures(path: Path) -> dict[str, list[dict[str, Any]]]:
    if not path.exists():
        return {"failures": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    failures = payload.get("failures", [])
    if not isinstance(failures, list):
        raise ValueError("failures must be a JSON array")
    result: list[dict[str, Any]] = []
    for failure in failures:
        if not isinstance(failure, dict):
            raise ValueError("failures must contain JSON objects")
        result.append(dict(failure))
    return {"failures": result}


def _failure_payload(config: QQRecordFailureConfig) -> dict[str, Any]:
    failure = {
        "date": config.date.strip(),
        "group": config.group_id.strip(),
        "status": config.status.strip(),
        "symptom": config.symptom.strip(),
    }
    for key, value in (
        ("observed_input", config.observed_input),
        ("decision_log_entry", config.decision_log_entry),
        ("send_or_capability_log_entry", config.send_or_capability_log_entry),
        ("root_cause", config.root_cause),
        ("fix", config.fix),
        ("regression_test", config.regression_test),
    ):
        if value.strip():
            failure[key] = value.strip()
    return failure


def _required_text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()
