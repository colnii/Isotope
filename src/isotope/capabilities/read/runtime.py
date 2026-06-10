"""Approval-gated local-file read runtime helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import json

from .core import FILE_READ_CAPABILITY, limited_int, read_text_excerpt


def request_local_file_read_approval(input_mapping: Mapping[str, Any]) -> dict[str, Any]:
    from isotope.runtime.in_process import InProcessServer

    root = Path(str(input_mapping["root"])).expanduser()
    path = str(input_mapping["path"])
    max_excerpt_chars = int(input_mapping["max_excerpt_chars"])
    api = InProcessServer(root)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal=f"Read local file: {path}")
    pending = api.submit_action(
        run["run_id"],
        {
            "action": "call_tool",
            "tool": "local_file_read",
            "path": path,
            "max_excerpt_chars": max_excerpt_chars,
            "summary": "Read one approved local file",
        },
        requires_approval=True,
    )
    return {
        "kind": "capability_run_result",
        "capability_id": FILE_READ_CAPABILITY,
        "status": "pending_user_approval",
        "runner_kind": "approval_gated_projection",
        "approval_id": pending["approval_id"],
        "read": {
            "scope": "local_file",
            "status": "pending_approval",
            "path": path,
            "approval_id": pending["approval_id"],
            "run_id": run["run_id"],
            "content_policy": "approval_required_before_read",
            "max_excerpt_chars": max_excerpt_chars,
        },
    }


def execute_local_file_read_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    path = payload.get("path")
    if not isinstance(path, str) or not path.strip():
        raise ValueError("path must be a non-empty string")
    max_excerpt_chars = limited_int(
        payload.get("max_excerpt_chars", 2000),
        field_name="max_excerpt_chars",
        minimum=1,
        maximum=8000,
    )
    target = Path(path).expanduser()
    return read_text_excerpt(
        target,
        path=str(target),
        scope="local_file",
        max_excerpt_chars=max_excerpt_chars,
    )


def local_file_read_artifact_content(read_result: dict[str, Any]) -> str:
    return json.dumps(read_result, ensure_ascii=False, sort_keys=True)
