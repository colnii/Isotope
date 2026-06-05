"""Build QQ beta closeout reports for operator send-run decisions."""

from __future__ import annotations

import json
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SEND_RUN_COMMAND = "ISOTOPE_QQ_ENABLE_SEND=1 ./send-run.sh"


@dataclass(frozen=True)
class QQBetaCloseoutConfig:
    beta_day_report: Path
    regression_intake: Path
    output: Path

    def __post_init__(self) -> None:
        _required_path(self.beta_day_report, "beta-day-report")
        _required_path(self.regression_intake, "regression-intake")
        _required_path(self.output, "output")


def build_qq_beta_closeout(config: QQBetaCloseoutConfig) -> dict[str, Any]:
    beta_day = _read_json_object(config.beta_day_report)
    intake = _read_json_object(config.regression_intake)
    summary = _dict_value(beta_day, "summary")
    failures = _list_value(beta_day, "failures")
    warnings = _list_value(beta_day, "review_warnings")
    drafts = _list_value(intake, "drafts")

    open_failure_count = _int_value(summary, "open_failure_count")
    warning_count = _int_value(summary, "warning_count")
    failure_count = _int_value(summary, "failure_count")
    closed_failure_count = _closed_failure_count(failures)
    pending_draft_count = _int_value(intake, "draft_count")
    pending_replay_commands = _pending_replay_commands(drafts)
    pending_pytest_commands = _pending_pytest_commands(drafts)
    blockers = _blockers(
        ready_for_send=bool(beta_day.get("ready_for_send")),
        warning_count=warning_count,
        open_failure_count=open_failure_count,
        pending_draft_count=pending_draft_count,
    )
    can_enter_send_run = not blockers

    closeout_summary = {
        **summary,
        "failure_count": failure_count,
        "closed_failure_count": closed_failure_count,
        "open_failure_count": open_failure_count,
        "warning_count": warning_count,
        "pending_regression_draft_count": pending_draft_count,
    }
    return {
        "kind": "qq_beta_closeout",
        "can_enter_send_run": can_enter_send_run,
        "blockers": blockers,
        "summary": closeout_summary,
        "checklist": _checklist(
            warning_count=warning_count,
            open_failure_count=open_failure_count,
            pending_draft_count=pending_draft_count,
            can_enter_send_run=can_enter_send_run,
        ),
        "pending_replay_commands": pending_replay_commands,
        "pending_pytest_commands": pending_pytest_commands,
        "inputs": {
            "beta_day_report": str(config.beta_day_report),
            "regression_intake": str(config.regression_intake),
        },
        "review_warnings": warnings,
        "next_actions": _next_actions(
            blockers=blockers,
            pending_replay_commands=pending_replay_commands,
            pending_pytest_commands=pending_pytest_commands,
        ),
    }


def write_qq_beta_closeout(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _blockers(
    *,
    ready_for_send: bool,
    warning_count: int,
    open_failure_count: int,
    pending_draft_count: int,
) -> list[str]:
    blockers: list[str] = []
    if warning_count:
        blockers.append("review_dry_run_warnings")
    if open_failure_count:
        blockers.append("open_failures")
    if pending_draft_count:
        blockers.append("pending_regression_drafts")
    if not ready_for_send and not blockers:
        blockers.append("beta_day_report_not_ready")
    return blockers


def _checklist(
    *,
    warning_count: int,
    open_failure_count: int,
    pending_draft_count: int,
    can_enter_send_run: bool,
) -> list[dict[str, Any]]:
    return [
        {
            "name": "dry_run_review",
            "status": "pass" if warning_count == 0 else "blocked",
        },
        {
            "name": "failure_closeout",
            "status": "pass" if open_failure_count == 0 else "blocked",
        },
        {
            "name": "regression_replay",
            "status": "pass" if pending_draft_count == 0 else "blocked",
        },
        {
            "name": "send_run",
            "status": "ready" if can_enter_send_run else "blocked",
            "command": SEND_RUN_COMMAND,
        },
    ]


def _next_actions(
    *,
    blockers: list[str],
    pending_replay_commands: list[str],
    pending_pytest_commands: list[str],
) -> list[str]:
    if not blockers:
        return ["operator_review_before_send"]
    actions: list[str] = ["keep_send_guarded"]
    if "review_dry_run_warnings" in blockers:
        actions.append("review_dry_run_warnings")
    if "open_failures" in blockers:
        actions.append("close_open_failures")
    if pending_replay_commands:
        actions.append("run_pending_replay_commands")
    if pending_pytest_commands:
        actions.append("run_pending_pytest_commands")
    return actions


def _pending_replay_commands(drafts: list[Any]) -> list[str]:
    commands: list[str] = []
    for draft in drafts:
        if not isinstance(draft, dict):
            raise ValueError("regression-intake drafts must contain JSON objects")
        replay_json = str(draft.get("replay_json", "")).strip()
        if replay_json:
            commands.append(
                "isotope-social qq replay --config-json config.json --state-root state "
                f"--replay-json {shlex.quote(replay_json)} "
                "--output logs/replay-report.json --json"
            )
    return commands


def _pending_pytest_commands(drafts: list[Any]) -> list[str]:
    commands: list[str] = []
    for draft in drafts:
        if not isinstance(draft, dict):
            raise ValueError("regression-intake drafts must contain JSON objects")
        command = str(draft.get("pytest_command", "")).strip()
        if command:
            commands.append(command)
    return commands


def _closed_failure_count(failures: list[Any]) -> int:
    count = 0
    for failure in failures:
        if not isinstance(failure, dict):
            raise ValueError("failures must contain JSON objects")
        status = str(failure.get("status", "open")).strip().lower()
        if status in {"closed", "resolved", "fixed"}:
            count += 1
    return count


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


def _int_value(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key, 0)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _required_path(path: Path, name: str) -> None:
    if not str(path).strip():
        raise ValueError(f"{name} must be a non-empty path")
