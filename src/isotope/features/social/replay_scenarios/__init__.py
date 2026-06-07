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
        _scenario_file(
            config,
            filename="04-llm-participation-ordinary-silent.json",
            scenario_id="llm_participation_ordinary_silent",
            purpose="Require replayed LLM participation to stay silent for ordinary chatter.",
        ),
        _scenario_file(
            config,
            filename="05-llm-participation-ordinary-respond.json",
            scenario_id="llm_participation_ordinary_respond",
            purpose="Require replayed LLM participation to respond to a useful ordinary message.",
        ),
        _scenario_file(
            config,
            filename="06-llm-participation-mention-respond.json",
            scenario_id="llm_participation_mention_respond",
            purpose="Require replayed LLM participation to respond when the bot is mentioned.",
        ),
        _scenario_file(
            config,
            filename="07-llm-participation-error-silent.json",
            scenario_id="llm_participation_error_silent",
            purpose="Require participation provider errors to become a silent candidate.",
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
    if scenario_id == "llm_participation_ordinary_silent":
        payload["events"] = [
            _ordinary_event(
                group_id=config.group_id,
                text="今晚大家闲聊一下游戏更新。",
            )
        ]
        payload["runtime"] = {
            "wake_keywords": [],
            "autonomy_score": 0.0,
            "replay_participation_decision": {
                "action": "silent",
                "reason": "ordinary_chatter",
                "confidence": 0.74,
            },
        }
        payload["expectations"] = _participation_expectations(
            min_silent_actions=1,
            actions=["silent"],
            reasons=["ordinary_chatter"],
        )
        return payload
    if scenario_id == "llm_participation_ordinary_respond":
        payload["events"] = [
            _ordinary_event(
                group_id=config.group_id,
                text="这个 PR 今天能合吗？",
            )
        ]
        payload["runtime"] = {
            "wake_keywords": [],
            "autonomy_score": 0.0,
            "replay_participation_decision": {
                "action": "respond",
                "reason": "topic_fit",
                "confidence": 0.83,
                "text": "能合，先确认 CI 全绿。",
            },
        }
        payload["expectations"] = _participation_expectations(
            min_respond_actions=1,
            actions=["respond"],
            reasons=["topic_fit"],
        )
        return payload
    if scenario_id == "llm_participation_mention_respond":
        payload["events"] = [payload["events"][0]]
        payload["runtime"] = {
            "wake_keywords": [],
            "autonomy_score": 0.0,
            "replay_participation_decision": {
                "action": "respond",
                "reason": "direct_mention",
                "confidence": 0.91,
                "text": "我看一下，先按测试结果判断。",
            },
        }
        payload["expectations"] = _participation_expectations(
            min_respond_actions=1,
            actions=["respond"],
            reasons=["direct_mention"],
        )
        return payload
    if scenario_id == "llm_participation_error_silent":
        payload["events"] = [payload["events"][0]]
        payload["runtime"] = {
            "wake_keywords": [],
            "autonomy_score": 0.0,
            "replay_participation_error": "bad model output",
        }
        payload["expectations"] = {
            **_participation_expectations(min_silent_actions=1),
            "min_participation_provider_errors": 1,
        }
        return payload
    raise ValueError(f"unsupported replay scenario: {scenario_id}")


def _participation_expectations(
    *,
    min_silent_actions: int = 0,
    min_respond_actions: int = 0,
    actions: list[str] | None = None,
    reasons: list[str] | None = None,
) -> dict[str, Any]:
    expectations: dict[str, Any] = {
        "require_processed_events": 1,
        "min_proposed_actions": 1,
        "max_send_feedback": 0,
        "max_sent_group_messages": 0,
        "require_all_dry_run": True,
    }
    if min_silent_actions:
        expectations["min_silent_actions"] = min_silent_actions
    if min_respond_actions:
        expectations["min_respond_actions"] = min_respond_actions
    if actions is not None:
        expectations["require_participation_actions"] = actions
    if reasons is not None:
        expectations["require_participation_reasons"] = reasons
    return expectations


def _ordinary_event(*, group_id: str, text: str) -> dict[str, Any]:
    return {
        "message_id": 9101,
        "message_type": "group",
        "group_id": int(group_id),
        "user_id": 10003,
        "sender": {"nickname": "阿陈", "role": "member"},
        "time": 1780560120,
        "message": [{"type": "text", "data": {"text": text}}],
        "raw_message": text,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _required_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()
