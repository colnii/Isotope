from __future__ import annotations

import json

from isotope.runtime.in_process import InProcessServer


def _create_run(root):
    api = InProcessServer(root)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="read local file")
    return api, run["run_id"]


def test_local_file_read_requires_approval_before_reading(tmp_path) -> None:
    target = tmp_path / "resume.md"
    target.write_text("private resume excerpt\n", encoding="utf-8")
    api, run_id = _create_run(tmp_path / "state")

    result = api.submit_action(
        run_id,
        {
            "action": "call_tool",
            "tool": "local_file_read",
            "path": str(target),
            "max_excerpt_chars": 2000,
            "summary": "Read one approved local file",
        },
        requires_approval=True,
    )

    assert result["status"] == "pending_user_approval"
    assert api.get_pending_approvals(run_id)[0]["status"] == "pending"
    artifact_dir = tmp_path / "state" / "runs" / run_id / "artifacts"
    assert not artifact_dir.exists()


def test_approved_local_file_read_writes_bounded_artifact(tmp_path) -> None:
    target = tmp_path / "resume.md"
    target.write_text("abcdef", encoding="utf-8")
    api, run_id = _create_run(tmp_path / "state")
    pending = api.submit_action(
        run_id,
        {
            "action": "call_tool",
            "tool": "local_file_read",
            "path": str(target),
            "max_excerpt_chars": 3,
            "summary": "Read one approved local file",
        },
        requires_approval=True,
    )

    resolved = api.resolve_approval(
        pending["approval_id"],
        {
            "resolution": "approved",
            "reason": "test approval",
            "resolver": "pytest",
        },
    )

    assert resolved["status"] == "completed"
    artifact_ref = resolved["artifact_ref"]
    content = api.artifact_store.get_content(artifact_ref)
    read = json.loads(content)
    assert read["scope"] == "local_file"
    assert read["status"] == "readable"
    assert read["excerpt"] == "abc"
    assert read["truncated"] is True


def test_denied_local_file_read_does_not_read_file(tmp_path) -> None:
    target = tmp_path / "resume.md"
    target.write_text("abcdef", encoding="utf-8")
    api, run_id = _create_run(tmp_path / "state")
    pending = api.submit_action(
        run_id,
        {
            "action": "call_tool",
            "tool": "local_file_read",
            "path": str(target),
            "max_excerpt_chars": 3,
            "summary": "Read one approved local file",
        },
        requires_approval=True,
    )

    resolved = api.resolve_approval(
        pending["approval_id"],
        {
            "resolution": "denied",
            "reason": "test denial",
            "resolver": "pytest",
        },
    )

    assert resolved["status"] == "denied"
    artifact_dir = tmp_path / "state" / "runs" / run_id / "artifacts"
    assert not artifact_dir.exists()
