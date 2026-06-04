"""Screen artifact inspection and public reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from isotope.platform.schemas.refs import make_artifact_ref
from isotope.workspace.artifacts import ArtifactStore


def inspect_screen_artifact(root: Path, *, run_id: str, artifact_id: str) -> dict[str, Any]:
    ref = make_artifact_ref(run_id=run_id, artifact_id=artifact_id)
    store = ArtifactStore(root)
    metadata = store.get_metadata(ref, include_provenance=True)
    if not _is_screen_artifact_type(str(metadata["artifact_type"])):
        raise ValueError("artifact is not a screen artifact")
    return {
        "status": "ok",
        "artifact": {
            **metadata,
            "ref": ref.to_dict(),
        },
        "content": _decode_json_content(store.get_content(ref)),
    }


def report_screen_artifacts(root: Path, *, run_id: str) -> dict[str, Any]:
    store = ArtifactStore(root)
    artifacts = [
        artifact
        for artifact in store.list_artifacts(run_id)
        if _is_screen_artifact_type(artifact.artifact_type)
    ]
    artifact_records: list[dict[str, Any]] = []
    metadata_payloads: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    control_plans: list[dict[str, Any]] = []
    control_results: list[dict[str, Any]] = []
    screenshot_count = 0
    for artifact in artifacts:
        record = {
            "run_id": artifact.run_id,
            "artifact_id": artifact.artifact_id,
            "artifact_type": artifact.artifact_type,
            "summary": artifact.summary,
            "ref": artifact.ref.to_dict(),
        }
        artifact_records.append(record)
        content = _decode_json_content(artifact.content)
        if artifact.artifact_type == "screen_metadata" and isinstance(content, dict):
            metadata_payloads.append(content)
        elif artifact.artifact_type == "screen_diagnostic":
            diagnostics.append(_screen_diagnostic_summary(record, content))
        elif artifact.artifact_type == "screen_screenshot":
            screenshot_count += 1
        elif artifact.artifact_type == "screen_control_plan":
            control_plans.append(_screen_control_summary(record, content))
        elif artifact.artifact_type == "screen_control_result":
            control_results.append(_screen_control_summary(record, content))

    reason_codes = [
        item["reason_code"]
        for item in diagnostics
        if isinstance(item.get("reason_code"), str) and item["reason_code"]
    ]
    control_actions = [*control_plans, *control_results]
    summary = {
        "artifact_count": len(artifact_records),
        "metadata_count": len(metadata_payloads),
        "diagnostic_count": len(diagnostics),
        "control_plan_count": len(control_plans),
        "control_result_count": len(control_results),
        "control_status": _screen_control_status(
            plan_count=len(control_plans),
            result_count=len(control_results),
        ),
        "control_actions": control_actions,
        "approval_required": bool(control_plans),
        "interferes_with_screen": bool(control_actions),
        "screenshot_count": screenshot_count,
        "screenshot_available": screenshot_count > 0,
        "observe_status": _screen_observe_status(
            metadata_count=len(metadata_payloads),
            screenshot_count=screenshot_count,
            reason_codes=reason_codes,
        ),
        "target": _latest_target(metadata_payloads),
        "matched_count": _latest_value(metadata_payloads, "matched_count"),
        "selected_window_id": _latest_value(metadata_payloads, "selected_window_id"),
        "selection_reason": _latest_value(metadata_payloads, "selection_reason"),
        "diagnostics": diagnostics,
        "recovery_actions": _unique_strings(
            item.get("recovery") for item in diagnostics if isinstance(item.get("recovery"), str)
        ),
    }
    return {
        "status": "ok",
        "run_id": run_id,
        "summary": summary,
        "artifacts": artifact_records,
    }


def print_screen_inspect_plain(payload: dict[str, Any]) -> None:
    artifact = payload["artifact"]
    ref = artifact["ref"]
    print(f"status: {payload['status']}")
    print(f"artifact: {artifact['artifact_type']} {ref['artifact_id']}")
    print(f"run: {ref['run_id']}")
    print(f"summary: {artifact['summary']}")
    content = payload["content"]
    if isinstance(content, (dict, list)):
        print(json.dumps(content, ensure_ascii=False, sort_keys=True))
    else:
        print(str(content))


def print_screen_report_plain(payload: dict[str, Any]) -> None:
    summary = payload["summary"]
    print(f"status: {payload['status']}")
    print(f"run: {payload['run_id']}")
    print(f"observe: {summary['observe_status']}")
    screenshot = "available" if summary["screenshot_available"] else "unavailable"
    print(f"screenshot: {screenshot}")
    target = summary.get("target")
    if isinstance(target, dict):
        print(
            "target: "
            f"app={target.get('app', '')} "
            f"title={target.get('title', '')} "
            f"window_id={target.get('window_id', '')} "
            f"minimized={str(target.get('is_minimized', False)).lower()}"
        )
    if summary.get("matched_count") is not None:
        print(f"matched: {summary['matched_count']}")
    if summary.get("selection_reason") is not None:
        print(f"selection: {summary['selection_reason']}")
    for recovery in summary.get("recovery_actions", []):
        print(f"recovery: {recovery}")
    if summary.get("control_status") != "none":
        print(f"control: {summary['control_status']}")
        approval = "required" if summary.get("approval_required") else "not_required"
        print(f"approval: {approval}")
        print(f"interference: {str(summary.get('interferes_with_screen', False)).lower()}")
        for action in summary.get("control_actions", []):
            if not isinstance(action, dict):
                continue
            action_types = action.get("action_types")
            if not isinstance(action_types, list) or not action_types:
                action_types = ["unknown"]
            print(
                "action: "
                f"{','.join(str(action_type) for action_type in action_types)} "
                f"count={action.get('action_count', 0)} "
                f"executed={str(action.get('executed', False)).lower()}"
            )
    for artifact in payload.get("artifacts", []):
        print(
            "artifact: "
            f"{artifact.get('artifact_type', '')} "
            f"{artifact.get('artifact_id', '')} "
            f"{artifact.get('summary', '')}"
        )


def _is_screen_artifact_type(artifact_type: str) -> bool:
    return artifact_type.startswith("screen_")


def _decode_json_content(content: str) -> Any:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return content


def _screen_diagnostic_summary(record: dict[str, Any], content: Any) -> dict[str, Any]:
    summary = {
        "artifact_id": record["artifact_id"],
        "summary": record["summary"],
    }
    if isinstance(content, dict):
        reason_code = content.get("reason_code")
        recovery = content.get("recovery")
        if isinstance(reason_code, str):
            summary["reason_code"] = reason_code
        if isinstance(recovery, str):
            summary["recovery"] = recovery
    return summary


def _screen_control_summary(record: dict[str, Any], content: Any) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "artifact_id": record["artifact_id"],
        "action_count": 0,
        "executed": False,
        "action_types": [],
    }
    if not isinstance(content, dict):
        return summary
    action_count = content.get("action_count")
    if isinstance(action_count, int) and action_count >= 0:
        summary["action_count"] = action_count
    executed = content.get("executed")
    if isinstance(executed, bool):
        summary["executed"] = executed
    planned_actions = content.get("planned_actions")
    if isinstance(planned_actions, list):
        summary["action_types"] = [
            action_type
            for action_type in planned_actions
            if isinstance(action_type, str) and action_type
        ]
    return summary


def _latest_target(metadata_payloads: list[dict[str, Any]]) -> dict[str, Any] | None:
    for payload in reversed(metadata_payloads):
        target = payload.get("target")
        if isinstance(target, dict):
            return dict(target)
    return None


def _latest_value(metadata_payloads: list[dict[str, Any]], key: str) -> Any:
    for payload in reversed(metadata_payloads):
        value = payload.get(key)
        if value is not None:
            return value
    return None


def _screen_observe_status(
    *,
    metadata_count: int,
    screenshot_count: int,
    reason_codes: list[str],
) -> str:
    if screenshot_count > 0:
        return "captured"
    if metadata_count > 0 or "screen_screenshot_unavailable" in reason_codes:
        return "metadata_only"
    return "no_screen_artifacts"


def _screen_control_status(*, plan_count: int, result_count: int) -> str:
    if result_count > 0:
        return "completed"
    if plan_count > 0:
        return "planned"
    return "none"


def _unique_strings(values: Any) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value not in seen:
            unique.append(value)
            seen.add(value)
    return unique
