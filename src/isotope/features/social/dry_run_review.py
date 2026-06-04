"""Operator review reports for QQ dry-run decisions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


STATE_FILENAME = "social-qq-state.json"


@dataclass(frozen=True)
class QQDryRunReviewConfig:
    state_file: Path
    group_id: str
    output: Path

    def __post_init__(self) -> None:
        if not str(self.state_file).strip():
            raise ValueError("state-file must be a non-empty path")
        if not isinstance(self.group_id, str) or not self.group_id.strip():
            raise ValueError("group must be a non-empty string")
        if not str(self.output).strip():
            raise ValueError("output must be a non-empty path")


def build_qq_dry_run_review(config: QQDryRunReviewConfig) -> dict[str, Any]:
    state = _read_json(config.state_file)
    audit_entries = state.get("audit_entries", [])
    if not isinstance(audit_entries, list):
        raise ValueError("state audit_entries must be a list")
    decision_entries = [
        entry
        for entry in audit_entries
        if isinstance(entry, dict)
        and entry.get("kind") == "decision"
        and str(entry.get("group_id")) == config.group_id
    ]
    turns = [_review_turn(index + 1, entry) for index, entry in enumerate(decision_entries)]
    summary = _summary(turns)
    warnings = _warnings(summary=summary, turns=turns)
    return {
        "kind": "qq_dry_run_review",
        "state_file": str(config.state_file),
        "group_id": config.group_id,
        "ready_for_send": False,
        "summary": summary,
        "turns": turns,
        "warnings": warnings,
    }


def write_qq_dry_run_review(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _review_turn(index: int, entry: dict[str, Any]) -> dict[str, Any]:
    payload = entry.get("payload", {})
    if not isinstance(payload, dict):
        payload = {}
    proposed = [_candidate_review(item) for item in _list_field(payload, "proposed")]
    selected = [_candidate_review(item) for item in _list_field(payload, "selected")]
    rejected = payload.get("rejected", {})
    if not isinstance(rejected, dict):
        rejected = {}
    wake_reason = _first_reason(proposed) or _first_reason(selected) or ""
    return {
        "index": index,
        "timestamp": str(entry.get("timestamp", "")),
        "dry_run": payload.get("dry_run") is True,
        "wake_reason": wake_reason,
        "proposed": proposed,
        "selected": selected,
        "rejected": dict(rejected),
        "send_feedback_count": 0,
    }


def _candidate_review(candidate: object) -> dict[str, Any]:
    if not isinstance(candidate, dict):
        return {}
    review = {
        "candidate_id": str(candidate.get("candidate_id", "")),
        "kind": str(candidate.get("kind", "")),
        "reason": str(candidate.get("reason", "")),
        "confidence": candidate.get("confidence"),
    }
    sticker = _sticker_from_candidate(candidate)
    if sticker is not None:
        review["sticker"] = sticker
    reply_preview = _reply_preview(candidate)
    if reply_preview:
        review["reply_preview"] = reply_preview
    return review


def _sticker_from_candidate(candidate: dict[str, Any]) -> dict[str, Any] | None:
    metadata = candidate.get("metadata", {})
    if isinstance(metadata, dict):
        selection = metadata.get("sticker_selection")
        if isinstance(selection, dict):
            entry = selection.get("entry", {})
            if isinstance(entry, dict):
                return {
                    "sticker_id": str(entry.get("sticker_id", "")),
                    "pack_id": str(entry.get("pack_id", "")),
                    "meaning": str(entry.get("meaning", "")),
                    "reasons": list(selection.get("reasons", []))
                    if isinstance(selection.get("reasons", []), list)
                    else [],
                }
    action = candidate.get("reply_action", {})
    if not isinstance(action, dict):
        return None
    for part in _list_field(action, "parts"):
        if isinstance(part, dict) and part.get("kind") == "sticker":
            platform_data = part.get("platform_data", {})
            if not isinstance(platform_data, dict):
                platform_data = {}
            return {
                "sticker_id": str(platform_data.get("sticker_id", "")),
                "pack_id": str(platform_data.get("pack_id", "")),
                "meaning": "",
                "reasons": list(platform_data.get("reasons", []))
                if isinstance(platform_data.get("reasons", []), list)
                else [],
            }
    return None


def _reply_preview(candidate: dict[str, Any]) -> str:
    action = candidate.get("reply_action", {})
    if not isinstance(action, dict):
        return ""
    previews: list[str] = []
    for part in _list_field(action, "parts"):
        if not isinstance(part, dict):
            continue
        if part.get("kind") == "text":
            previews.append(str(part.get("text", "")))
        elif part.get("kind") == "sticker":
            sticker = _sticker_from_candidate(candidate) or {}
            previews.append(f"[sticker:{sticker.get('sticker_id', '')}]")
        else:
            previews.append(f"[{part.get('kind', 'part')}]")
    return " ".join(item for item in previews if item)


def _summary(turns: list[dict[str, Any]]) -> dict[str, int]:
    proposed = sum(len(_list_field(turn, "proposed")) for turn in turns)
    selected = sum(len(_list_field(turn, "selected")) for turn in turns)
    rejected = sum(len(_dict_field(turn, "rejected")) for turn in turns)
    stickers = sum(
        1
        for turn in turns
        for candidate in _list_field(turn, "proposed")
        if isinstance(candidate, dict) and isinstance(candidate.get("sticker"), dict)
    )
    feedback = sum(_int_field(turn, "send_feedback_count") for turn in turns)
    return {
        "decision_count": len(turns),
        "dry_run_decision_count": sum(1 for turn in turns if turn.get("dry_run") is True),
        "proposed_action_count": proposed,
        "selected_action_count": selected,
        "rejected_action_count": rejected,
        "sticker_candidate_count": stickers,
        "send_feedback_count": feedback,
    }


def _warnings(*, summary: dict[str, int], turns: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    if summary["decision_count"] == 0:
        warnings.append("no_decisions_recorded")
    if summary["dry_run_decision_count"] != summary["decision_count"]:
        warnings.append("non_dry_run_decisions_present")
    if summary["proposed_action_count"] > 0 and summary["selected_action_count"] == 0:
        warnings.append("dry_run_candidates_not_selected")
    if summary["sticker_candidate_count"] == 0:
        warnings.append("no_sticker_candidates")
    if any(_dict_field(turn, "rejected") for turn in turns):
        warnings.append("rejected_candidates_present")
    return warnings


def _first_reason(candidates: list[object]) -> str | None:
    for candidate in candidates:
        if isinstance(candidate, dict):
            reason = candidate.get("reason")
            if isinstance(reason, str) and reason:
                return reason
    return None


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _list_field(payload: dict[str, Any], key: str) -> list[object]:
    value = payload.get(key, [])
    if not isinstance(value, list):
        return []
    return list(value)


def _dict_field(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key, {})
    if not isinstance(value, dict):
        return {}
    return dict(value)


def _int_field(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key, 0)
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return value
