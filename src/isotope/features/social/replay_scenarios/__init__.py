"""Generated QQ replay scenario packs for role-card and sticker tuning."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..replay import (
    DEFAULT_REPLAY_EXPECTATIONS,
    DEFAULT_REPLAY_RUNTIME,
    QQReplayTemplateConfig,
    qq_replay_template_payload,
)


@dataclass(frozen=True)
class QQReplayScenariosConfig:
    output_dir: Path
    group_id: str
    bot_user_id: str

    def __post_init__(self) -> None:
        _required_text(str(self.output_dir), "output_dir")
        _required_text(self.group_id, "group")
        _required_text(self.bot_user_id, "bot_user_id")


@dataclass(frozen=True)
class QQReplayScenarioFile:
    scenario_id: str
    path: Path
    purpose: str
    replay_command: str

    def __post_init__(self) -> None:
        _required_text(self.scenario_id, "scenario_id")
        _required_text(str(self.path), "scenario path")
        _required_text(self.purpose, "scenario purpose")
        _required_text(self.replay_command, "scenario replay_command")

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "path": str(self.path),
            "purpose": self.purpose,
            "replay_command": self.replay_command,
        }


@dataclass(frozen=True)
class QQReplayScenariosResult:
    output_dir: Path
    scenarios: tuple[QQReplayScenarioFile, ...]
    index_path: Path

    def __post_init__(self) -> None:
        _required_text(str(self.output_dir), "output_dir")
        if not isinstance(self.scenarios, tuple) or not self.scenarios:
            raise ValueError("replay scenarios must be a non-empty tuple")
        for scenario in self.scenarios:
            if not isinstance(scenario, QQReplayScenarioFile):
                raise ValueError("replay scenarios items must be QQReplayScenarioFile")
        _required_text(str(self.index_path), "index_path")

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "output_dir": str(self.output_dir),
            "scenario_count": len(self.scenarios),
            "scenario_files": [str(scenario.path) for scenario in self.scenarios],
            "index_path": str(self.index_path),
            "scenarios": [scenario.to_public_dict() for scenario in self.scenarios],
        }


def create_qq_replay_scenarios(
    config: QQReplayScenariosConfig,
) -> QQReplayScenariosResult:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    scenarios = tuple(_scenario_files(config))
    for scenario in scenarios:
        _write_json(scenario.path, _scenario_payload(config, scenario.scenario_id))
    index_path = config.output_dir / "index.json"
    _write_json(
        index_path,
        {
            "kind": "qq_replay_scenarios",
            "group_id": config.group_id,
            "bot_user_id": config.bot_user_id,
            "scenarios": [scenario.to_public_dict() for scenario in scenarios],
        },
    )
    return QQReplayScenariosResult(
        output_dir=config.output_dir,
        scenarios=scenarios,
        index_path=index_path,
    )


def _scenario_files(config: QQReplayScenariosConfig) -> tuple[QQReplayScenarioFile, ...]:
    return (
        _scenario_file(
            config,
            filename="01-ship-it-candidate.json",
            scenario_id="ship_it_candidate",
            purpose="Require the ship-it sticker candidate in the controlled group.",
        ),
        _scenario_file(
            config,
            filename="02-no-matching-sticker.json",
            scenario_id="no_matching_sticker",
            purpose="Require no_matching_sticker when emotion and scene tags do not match.",
        ),
        _scenario_file(
            config,
            filename="03-forbid-frequency-zero.json",
            scenario_id="forbid_frequency_zero",
            purpose="Fail when role-card sticker frequency accidentally disables stickers.",
        ),
    )


def _scenario_file(
    config: QQReplayScenariosConfig,
    *,
    filename: str,
    scenario_id: str,
    purpose: str,
) -> QQReplayScenarioFile:
    return QQReplayScenarioFile(
        scenario_id=scenario_id,
        path=config.output_dir / filename,
        purpose=purpose,
        replay_command=(
            "isotope-social qq replay --config-json <config.json> "
            "--state-root <state-dir> "
            f"--replay-json {filename} "
            f"--output logs/{filename.removesuffix('.json')}-report.json --json"
        ),
    )


def _scenario_payload(
    config: QQReplayScenariosConfig,
    scenario_id: str,
) -> dict[str, Any]:
    payload = qq_replay_template_payload(
        QQReplayTemplateConfig(
            output=config.output_dir / "_unused.json",
            group_id=config.group_id,
            bot_user_id=config.bot_user_id,
        )
    )
    payload["name"] = f"QQ replay scenario: {scenario_id}"
    if scenario_id == "ship_it_candidate":
        payload["expectations"] = {
            **dict(DEFAULT_REPLAY_EXPECTATIONS),
            "require_processed_events": 2,
            "min_sticker_candidates": 1,
            "require_sticker_candidate_ids": ["ship-it"],
            "forbid_sticker_block_reasons": [
                "use_frequency_zero",
                "no_matching_sticker",
                "recent_sticker_feedback",
            ],
        }
        return payload
    if scenario_id == "no_matching_sticker":
        payload["runtime"] = {
            **dict(DEFAULT_REPLAY_RUNTIME),
            "sticker_emotion": "unmatched",
            "sticker_scene_tags": ["unmatched-scene"],
        }
        payload["expectations"] = {
            **dict(DEFAULT_REPLAY_EXPECTATIONS),
            "min_sticker_candidates": 0,
            "require_sticker_candidate_ids": [],
            "require_sticker_block_reasons": ["no_matching_sticker"],
            "forbid_sticker_block_reasons": ["use_frequency_zero"],
        }
        return payload
    if scenario_id == "forbid_frequency_zero":
        payload["expectations"] = {
            **dict(DEFAULT_REPLAY_EXPECTATIONS),
            "min_sticker_candidates": 1,
            "require_sticker_candidate_ids": ["ship-it"],
            "forbid_sticker_block_reasons": ["use_frequency_zero"],
        }
        return payload
    raise ValueError(f"unsupported replay scenario: {scenario_id}")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _required_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()
