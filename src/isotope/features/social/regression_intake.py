"""Create QQ replay drafts from beta failure records."""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .replay import DEFAULT_REPLAY_RUNTIME


DRAFT_REPLAY_EXPECTATIONS = {
    "require_processed_events": 1,
    "min_proposed_actions": 1,
    "max_send_feedback": 0,
    "max_sent_group_messages": 0,
    "require_all_dry_run": True,
}


@dataclass(frozen=True)
class QQRegressionIntakeConfig:
    group_id: str
    bot_user_id: str
    failures_json: Path
    output_dir: Path
    index_output: Path

    def __post_init__(self) -> None:
        _required_text(self.group_id, "group")
        _required_text(self.bot_user_id, "bot_user_id")
        _required_path(self.failures_json, "failures-json")
        _required_path(self.output_dir, "output-dir")
        _required_path(self.index_output, "index-output")


def build_qq_regression_intake(config: QQRegressionIntakeConfig) -> dict[str, Any]:
    payload = _read_json_object(config.failures_json)
    failures = _failure_entries(payload)
    open_failures = [
        failure
        for failure in failures
        if _is_open_failure(failure) and _failure_group_matches(failure, config.group_id)
    ]
    drafts: list[dict[str, Any]] = []
    for index, failure in enumerate(open_failures, start=1):
        failure_id = _failure_id(failure, index=index)
        regression_test = _regression_test(failure)
        replay_path = config.output_dir / f"{_slug(failure_id)}.replay.json"
        replay = _replay_draft(
            failure=failure,
            failure_id=failure_id,
            group_id=config.group_id,
            bot_user_id=config.bot_user_id,
            message_id=910000 + index,
        )
        drafts.append(
            {
                "failure_id": failure_id,
                "symptom": str(failure.get("symptom", "")).strip(),
                "status": str(failure.get("status", "open")).strip() or "open",
                "regression_test": regression_test,
                "pytest_command": _pytest_command(regression_test),
                "replay_json": str(replay_path),
                "_replay": replay,
            }
        )
    return {
        "kind": "qq_regression_intake",
        "group_id": config.group_id,
        "source_failures_json": str(config.failures_json),
        "output_dir": str(config.output_dir),
        "open_failure_count": len(open_failures),
        "draft_count": len(drafts),
        "drafts": drafts,
    }


def write_qq_regression_intake(index_path: Path, intake: dict[str, Any]) -> None:
    public_intake = dict(intake)
    public_drafts: list[dict[str, Any]] = []
    for draft in intake.get("drafts", []):
        if not isinstance(draft, dict):
            raise ValueError("intake drafts must contain JSON objects")
        replay = draft.get("_replay")
        if not isinstance(replay, dict):
            raise ValueError("intake draft replay payload must be a JSON object")
        replay_path = Path(str(draft.get("replay_json", "")))
        _required_path(replay_path, "replay_json")
        replay_path.parent.mkdir(parents=True, exist_ok=True)
        _write_json(replay_path, replay)
        public_drafts.append({key: value for key, value in draft.items() if key != "_replay"})
    public_intake["drafts"] = public_drafts
    index_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(index_path, public_intake)


def _replay_draft(
    *,
    failure: dict[str, Any],
    failure_id: str,
    group_id: str,
    bot_user_id: str,
    message_id: int,
) -> dict[str, Any]:
    observed_input = _observed_input(failure)
    return {
        "schema_version": "isotope.qq_replay.v1",
        "name": f"QQ regression draft: {failure_id}",
        "metadata": {
            "failure_id": failure_id,
            "date": str(failure.get("date", "")).strip(),
            "group": group_id,
            "symptom": str(failure.get("symptom", "")).strip(),
            "root_cause": str(failure.get("root_cause", "")).strip(),
            "regression_test": str(failure.get("regression_test", "")).strip(),
        },
        "runtime": dict(DEFAULT_REPLAY_RUNTIME),
        "expectations": dict(DRAFT_REPLAY_EXPECTATIONS),
        "events": [
            {
                "message_id": message_id,
                "message_type": "group",
                "group_id": int(group_id),
                "user_id": 10001,
                "sender": {"nickname": "Beta复盘", "role": "member"},
                "time": 1780560000,
                "message": [
                    {"type": "at", "data": {"qq": bot_user_id}},
                    {"type": "text", "data": {"text": f" {observed_input}"}},
                ],
                "raw_message": f"[CQ:at,qq={bot_user_id}] {observed_input}",
            }
        ],
    }


def _observed_input(failure: dict[str, Any]) -> str:
    observed_input = str(failure.get("observed_input", "")).strip()
    if observed_input:
        return observed_input
    symptom = str(failure.get("symptom", "")).strip()
    if symptom:
        return symptom
    return "请复现这个 beta 失败。"


def _regression_test(failure: dict[str, Any]) -> str:
    return str(failure.get("regression_test", "")).strip()


def _pytest_command(regression_test: str) -> str:
    if not regression_test:
        return ""
    return (
        "PYTHONPATH=src .venv/bin/python -m pytest "
        f"{shlex.quote(regression_test)} -q"
    )


def _failure_entries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    failures = payload.get("failures", [])
    if not isinstance(failures, list):
        raise ValueError("failures must be a JSON array")
    result: list[dict[str, Any]] = []
    for failure in failures:
        if not isinstance(failure, dict):
            raise ValueError("failures must contain JSON objects")
        result.append(dict(failure))
    return result


def _is_open_failure(failure: dict[str, Any]) -> bool:
    status = str(failure.get("status", "open")).strip().lower()
    return status not in {"closed", "resolved", "fixed"}


def _failure_group_matches(failure: dict[str, Any], group_id: str) -> bool:
    group = failure.get("group")
    return group is None or str(group).strip() == group_id


def _failure_id(failure: dict[str, Any], *, index: int) -> str:
    value = str(failure.get("id", "")).strip()
    if value:
        return value
    return f"qq-failure-{index}"


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-")
    return slug or "qq-failure"


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _required_text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _required_path(path: Path, name: str) -> None:
    if not str(path).strip():
        raise ValueError(f"{name} must be a non-empty path")
