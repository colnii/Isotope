"""Replay-template command handlers for QQ social commands."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .qq_runtime_commands import run_qq_replay
from .qq_state_config import state_path
from .replay import QQReplayTemplateConfig, create_qq_replay_template
from .replay_scenarios import (
    QQReplayScenariosConfig,
    create_qq_replay_scenarios,
)


def handle_init_replay(args: argparse.Namespace) -> dict[str, Any]:
    result = create_qq_replay_template(
        QQReplayTemplateConfig(
            output=Path(args.output),
            group_id=args.group,
            bot_user_id=args.bot_user_id,
        )
    )
    payload = result.to_public_dict()
    payload.update({"status": "ok", "command": "init-replay"})
    return payload


def handle_init_replay_scenarios(args: argparse.Namespace) -> dict[str, Any]:
    result = create_qq_replay_scenarios(
        QQReplayScenariosConfig(
            output_dir=Path(args.output_dir),
            group_id=args.group,
            bot_user_id=args.bot_user_id,
        )
    )
    payload = result.to_public_dict()
    payload.update({"status": "ok", "command": "init-replay-scenarios"})
    return payload


def handle_replay_scenarios(args: argparse.Namespace) -> dict[str, Any]:
    scenario_dir = Path(args.scenario_dir)
    output_path = Path(args.output)
    reports_dir = (
        Path(args.reports_dir)
        if args.reports_dir
        else _default_reports_dir(output_path)
    )
    index = _load_scenario_index(scenario_dir)
    scenarios = []
    passed_count = 0
    for item in index["scenarios"]:
        scenario_id = _required_text(item.get("scenario_id"), "scenario_id")
        replay_path = _scenario_replay_path(scenario_dir, item)
        report_path = reports_dir / f"{replay_path.stem}-report.json"
        run_payload = run_qq_replay(
            config_path=Path(args.config_json),
            state_root=Path(args.state_root),
            replay_path=replay_path,
            output_path=report_path,
        )
        report = _read_json(report_path)
        passed = bool(report["passed"])
        if passed:
            passed_count += 1
        scenarios.append(
            {
                "scenario_id": scenario_id,
                "replay_json": str(replay_path),
                "report_json": str(report_path),
                "passed": passed,
                "expectations": report["expectations"],
                "summary": report["summary"],
                "processed_events": run_payload["processed_events"],
                "event_count": run_payload["event_count"],
            }
        )
    summary = {
        "scenario_count": len(scenarios),
        "passed_count": passed_count,
        "failed_count": len(scenarios) - passed_count,
    }
    passed = summary["failed_count"] == 0
    report = {
        "kind": "qq_replay_scenarios_report",
        "scenario_dir": str(scenario_dir),
        "config_json": str(Path(args.config_json)),
        "state_file": str(state_path(Path(args.state_root))),
        "reports_dir": str(reports_dir),
        "passed": passed,
        "summary": summary,
        "scenarios": scenarios,
    }
    _write_json(output_path, report)
    payload = {
        "status": "ok" if passed else "failed",
        "command": "replay-scenarios",
        "passed": passed,
        "scenario_count": summary["scenario_count"],
        "passed_count": summary["passed_count"],
        "failed_count": summary["failed_count"],
        "output": str(output_path),
        "reports_dir": str(reports_dir),
        "scenarios": [
            {
                "scenario_id": item["scenario_id"],
                "replay_json": item["replay_json"],
                "report_json": item["report_json"],
                "passed": item["passed"],
            }
            for item in scenarios
        ],
    }
    if not passed:
        payload["_exit_code"] = 2
    return payload


def _default_reports_dir(output_path: Path) -> Path:
    return output_path.parent / f"{output_path.stem}-reports"


def _load_scenario_index(scenario_dir: Path) -> dict[str, Any]:
    index_path = scenario_dir / "index.json"
    payload = _read_json(index_path)
    if payload.get("kind") != "qq_replay_scenarios":
        raise ValueError("scenario index kind must be qq_replay_scenarios")
    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("scenario index scenarios must be a non-empty list")
    for item in scenarios:
        if not isinstance(item, dict):
            raise ValueError("scenario index scenarios items must be JSON objects")
    return {"scenarios": [dict(item) for item in scenarios]}


def _scenario_replay_path(scenario_dir: Path, item: dict[str, Any]) -> Path:
    raw_path = _required_text(item.get("path"), "scenario path")
    replay_path = Path(raw_path)
    if replay_path.is_absolute() or replay_path.exists():
        return replay_path
    return scenario_dir / replay_path.name


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()
