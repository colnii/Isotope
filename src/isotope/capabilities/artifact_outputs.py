"""Artifact-backed native coding result artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .workspace_files import run_workspace_changed_files
from ..platform.schemas.input_contract import missing_required_input_keys
from ..workspace.artifacts import ArtifactStore


ARTIFACT_DIFF_RESULT_CAPABILITY = "artifact.diff_result"
ARTIFACT_CHANGED_FILES_CAPABILITY = "artifact.changed_files"
ARTIFACT_OUTPUT_CAPABILITIES = frozenset(
    {ARTIFACT_DIFF_RESULT_CAPABILITY, ARTIFACT_CHANGED_FILES_CAPABILITY}
)


def is_artifact_output_capability(capability_id: str) -> bool:
    return capability_id in ARTIFACT_OUTPUT_CAPABILITIES


def validate_artifact_output_inputs(
    *,
    capability_id: str,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    if capability_id not in ARTIFACT_OUTPUT_CAPABILITIES:
        return dict(inputs or {})
    input_mapping = dict(inputs or {})
    for name in ("root", "cwd", "workspace_id", "run_id", "execution_id"):
        if name in missing_inputs:
            continue
        value = input_mapping.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
        input_mapping[name] = value.strip()
    return input_mapping


def run_artifact_changed_files(*, inputs: Mapping[str, Any] | None) -> dict[str, Any]:
    return _run_artifact_result_artifact(
        capability_id=ARTIFACT_CHANGED_FILES_CAPABILITY,
        artifact_type="native_coding.changed_files",
        inputs=inputs,
    )


def run_artifact_diff_result(*, inputs: Mapping[str, Any] | None) -> dict[str, Any]:
    return _run_artifact_result_artifact(
        capability_id=ARTIFACT_DIFF_RESULT_CAPABILITY,
        artifact_type="native_coding.diff_result",
        inputs=inputs,
    )


def _run_artifact_result_artifact(
    *,
    capability_id: str,
    artifact_type: str,
    inputs: Mapping[str, Any] | None,
) -> dict[str, Any]:
    required_inputs = ["root", "cwd", "workspace_id", "run_id", "execution_id"]
    missing_inputs = _missing_inputs(required_inputs, inputs)
    if missing_inputs:
        raise ValueError("missing required capability inputs: " + ", ".join(missing_inputs))
    input_mapping = validate_artifact_output_inputs(
        capability_id=capability_id,
        inputs=inputs,
        missing_inputs=missing_inputs,
    )
    changed_result = run_workspace_changed_files(inputs=input_mapping)
    changed_payload = changed_result["changed_files"]
    content = _artifact_content(
        artifact_type=artifact_type,
        changed_payload=changed_payload,
    )
    description = _artifact_result_description(
        workspace_id=input_mapping["workspace_id"],
        changed_file_count=changed_payload["changed_file_count"],
    )
    artifact = ArtifactStore(Path(input_mapping["root"]).expanduser()).create_artifact(
        run_id=input_mapping["run_id"],
        execution_id=input_mapping["execution_id"],
        artifact_type=artifact_type,
        summary=description,
        content=json.dumps(content, sort_keys=True),
    )
    return {
        "kind": "capability_run_result",
        "capability_id": capability_id,
        "status": "completed",
        "runner_kind": "deterministic_local",
        "artifact": {
            "artifact_id": artifact.artifact_id,
            "artifact_type": artifact.artifact_type,
            "summary": artifact.summary,
            "ref": artifact.ref.to_dict(),
            "artifact_write": "performed",
            "event_append": "state_event_append_handoff",
            "content_policy": "diff_result_projection",
        },
    }


def _artifact_content(
    *,
    artifact_type: str,
    changed_payload: Mapping[str, Any],
) -> dict[str, Any]:
    changed_files = [dict(item) for item in changed_payload["changed_files"]]
    content: dict[str, Any] = {
        "artifact_type": artifact_type,
        "workspace_id": changed_payload["workspace_id"],
        "status": changed_payload["status"],
        "changed_file_count": changed_payload["changed_file_count"],
        "changed_files": changed_files,
        "include_paths": list(changed_payload["include_paths"]),
        "content_policy": "diff_result_projection",
        "event_append": "state_event_append_handoff",
    }
    if artifact_type == "native_coding.diff_result":
        content["result_lines"] = [
            f"{item['status']} {item['path']}" for item in changed_files
        ]
    return content


def _artifact_result_description(*, workspace_id: str, changed_file_count: int) -> str:
    noun = "file" if changed_file_count == 1 else "files"
    return f"{changed_file_count} changed {noun} in {workspace_id}"


def _missing_inputs(
    required_inputs: list[str], inputs: Mapping[str, Any] | None
) -> list[str]:
    return missing_required_input_keys(inputs, required_inputs)


__all__ = [
    "ARTIFACT_CHANGED_FILES_CAPABILITY",
    "ARTIFACT_DIFF_RESULT_CAPABILITY",
    "ARTIFACT_OUTPUT_CAPABILITIES",
    "is_artifact_output_capability",
    "run_artifact_changed_files",
    "run_artifact_diff_result",
    "validate_artifact_output_inputs",
]
