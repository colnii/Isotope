"""Beta and operations-report command handlers for QQ social commands."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .beta_check import QQBetaCheckConfig, check_qq_beta_pack
from .beta_day_report import (
    QQBetaDayReportConfig,
    build_qq_beta_day_report,
    write_qq_beta_day_report,
)
from .beta_diagnostics import QQBetaDiagnosticsConfig, build_qq_beta_diagnostics
from .beta_pack import QQBetaPackConfig, create_qq_beta_pack
from .dry_run_review import (
    QQDryRunReviewConfig,
    build_qq_dry_run_review,
    write_qq_dry_run_review,
)
from .failure_log import QQRecordFailureConfig, record_qq_beta_failure
from .qq_state_config import state_path
from .regression_intake import (
    QQRegressionIntakeConfig,
    build_qq_regression_intake,
    write_qq_regression_intake,
)
from .startup_gate import QQStartupGateConfig, check_qq_startup_gate


def handle_init_beta(args: argparse.Namespace) -> dict[str, Any]:
    result = create_qq_beta_pack(
        QQBetaPackConfig(
            output_dir=Path(args.output_dir),
            group_id=args.group,
            operator_user_id=args.operator,
            bot_user_id=args.bot_user_id,
            websocket_url=args.websocket_url,
            max_events=args.max_events,
            force=bool(args.force),
        )
    )
    payload = result.to_public_dict()
    payload.update({"status": "ok", "command": "init-beta"})
    return payload


def handle_beta_check(args: argparse.Namespace) -> dict[str, Any]:
    result = check_qq_beta_pack(QQBetaCheckConfig(pack_dir=Path(args.pack_dir)))
    payload = result.to_public_dict()
    payload.update({"status": "ok", "command": "beta-check"})
    return payload


def handle_beta_diagnostics(args: argparse.Namespace) -> dict[str, Any]:
    payload = build_qq_beta_diagnostics(
        QQBetaDiagnosticsConfig(pack_dir=Path(args.pack_dir))
    )
    payload["command"] = "beta-diagnostics"
    if payload["status"] != "ready":
        payload["_exit_code"] = 2
    return payload


def handle_startup_check(args: argparse.Namespace) -> dict[str, Any]:
    result = check_qq_startup_gate(
        QQStartupGateConfig(
            pack_dir=Path(args.pack_dir),
            replay_report=Path(args.replay_report),
            min_sticker_candidates=args.min_sticker_candidates,
        )
    )
    payload = result.to_public_dict()
    payload.update(
        {
            "status": "ok" if result.ready else "blocked",
            "command": "startup-check",
        }
    )
    if not result.ready:
        payload["_exit_code"] = 2
    return payload


def handle_review_dry_run(args: argparse.Namespace) -> dict[str, Any]:
    state_file = state_path(Path(args.state_root))
    output = Path(args.output)
    report = build_qq_dry_run_review(
        QQDryRunReviewConfig(
            state_file=state_file,
            group_id=str(args.group),
            output=output,
        )
    )
    write_qq_dry_run_review(output, report)
    return {
        "status": "ok",
        "command": "review-dry-run",
        "output": str(output),
        "ready_for_send": bool(report["ready_for_send"]),
        "summary": report["summary"],
        "warnings": report["warnings"],
    }


def handle_beta_day_report(args: argparse.Namespace) -> dict[str, Any]:
    output = Path(args.output)
    report = build_qq_beta_day_report(
        QQBetaDayReportConfig(
            date=args.date,
            group_id=str(args.group),
            dry_run_review=Path(args.dry_run_review),
            export_log=Path(args.export_log),
            failures_json=Path(args.failures_json) if args.failures_json else None,
            output=output,
        )
    )
    write_qq_beta_day_report(output, report)
    return {
        "status": "ok",
        "command": "beta-day-report",
        "output": str(output),
        "ready_for_send": bool(report["ready_for_send"]),
        "open_failure_count": int(report["summary"]["open_failure_count"]),
        "summary": report["summary"],
        "next_actions": report["next_actions"],
    }


def handle_regression_intake(args: argparse.Namespace) -> dict[str, Any]:
    index_output = Path(args.index_output)
    intake = build_qq_regression_intake(
        QQRegressionIntakeConfig(
            group_id=str(args.group),
            bot_user_id=str(args.bot_user_id),
            failures_json=Path(args.failures_json),
            output_dir=Path(args.output_dir),
            index_output=index_output,
        )
    )
    write_qq_regression_intake(index_output, intake)
    return {
        "status": "ok",
        "command": "regression-intake",
        "output_dir": str(args.output_dir),
        "index_output": str(index_output),
        "open_failure_count": int(intake["open_failure_count"]),
        "draft_count": int(intake["draft_count"]),
        "drafts": [
            str(draft["replay_json"])
            for draft in intake["drafts"]
            if isinstance(draft, dict)
        ],
    }


def handle_record_failure(args: argparse.Namespace) -> dict[str, Any]:
    result = record_qq_beta_failure(
        QQRecordFailureConfig(
            failures_json=Path(args.failures_json),
            date=args.date,
            group_id=str(args.group),
            status=args.status,
            symptom=args.symptom,
            observed_input=args.observed_input or "",
            decision_log_entry=args.decision_log_entry or "",
            send_or_capability_log_entry=args.send_or_capability_log_entry or "",
            root_cause=args.root_cause or "",
            fix=args.fix or "",
            regression_test=args.regression_test or "",
        )
    )
    return {"status": "ok", "command": "record-failure", **result}
