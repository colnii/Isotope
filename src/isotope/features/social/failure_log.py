"""Append structured QQ beta failure records."""

from __future__ import annotations

import json
import re
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


@dataclass(frozen=True)
class QQCloseFailureConfig:
    failures_json: Path
    group_id: str
    failure: str
    resolved_date: str
    fix: str
    status: str = "fixed"
    regression_test: str = ""

    def __post_init__(self) -> None:
        if not str(self.failures_json).strip():
            raise ValueError("failures-json must be a non-empty path")
        _required_text(self.group_id, "group")
        _required_text(self.failure, "failure")
        _required_text(self.resolved_date, "resolved-date")
        _required_text(self.fix, "fix")
        _required_text(self.status, "status")
        if self.status.strip().lower() not in {"fixed", "resolved", "closed"}:
            raise ValueError("status must be fixed, resolved, or closed")


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


def close_qq_beta_failure(config: QQCloseFailureConfig) -> dict[str, Any]:
    payload = _read_failures(config.failures_json)
    failures = payload["failures"]
    match_index = _failure_match_index(
        failures,
        group_id=config.group_id,
        failure_ref=config.failure,
    )
    updated = dict(failures[match_index])
    updated["status"] = config.status.strip().lower()
    updated["resolved_date"] = config.resolved_date.strip()
    updated["fix"] = config.fix.strip()
    if config.regression_test.strip():
        updated["regression_test"] = config.regression_test.strip()
    failures[match_index] = updated
    config.failures_json.parent.mkdir(parents=True, exist_ok=True)
    config.failures_json.write_text(
        json.dumps({"failures": failures}, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return {
        "failures_json": str(config.failures_json),
        "failure_count": len(failures),
        "open_failure_count": sum(1 for failure in failures if _is_open_failure(failure)),
        "failure": updated,
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


def _failure_match_index(
    failures: list[dict[str, Any]],
    *,
    group_id: str,
    failure_ref: str,
) -> int:
    ref = failure_ref.strip()
    id_matches = [
        index
        for index, failure in enumerate(failures)
        if str(failure.get("id", "")).strip() == ref
    ]
    if id_matches:
        return _single_match(id_matches, ref)
    generated_id_match = re.fullmatch(r"qq-failure-(\d+)", ref)
    if generated_id_match:
        generated_match = _generated_failure_match(
            failures,
            group_id=group_id,
            generated_index=int(generated_id_match.group(1)),
        )
        if generated_match is not None:
            return generated_match
    symptom_matches = [
        index
        for index, failure in enumerate(failures)
        if str(failure.get("group", "")).strip() == group_id.strip()
        and str(failure.get("symptom", "")).strip() == ref
    ]
    return _single_match(symptom_matches, ref)


def _generated_failure_match(
    failures: list[dict[str, Any]],
    *,
    group_id: str,
    generated_index: int,
) -> int | None:
    if generated_index <= 0:
        return None
    open_group_indexes = [
        index
        for index, failure in enumerate(failures)
        if _failure_group_matches(failure, group_id) and _is_open_failure(failure)
    ]
    if generated_index > len(open_group_indexes):
        return None
    return open_group_indexes[generated_index - 1]


def _failure_group_matches(failure: dict[str, Any], group_id: str) -> bool:
    group = failure.get("group")
    return group is None or str(group).strip() == group_id.strip()


def _single_match(matches: list[int], ref: str) -> int:
    if not matches:
        raise ValueError(f"no matching failure: {ref}")
    if len(matches) > 1:
        raise ValueError(f"multiple matching failures: {ref}")
    return matches[0]


def _is_open_failure(failure: dict[str, Any]) -> bool:
    status = str(failure.get("status", "open")).strip().lower()
    return status not in {"closed", "resolved", "fixed"}


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
