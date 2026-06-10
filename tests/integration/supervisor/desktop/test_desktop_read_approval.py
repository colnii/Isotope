from __future__ import annotations

from isotope.features.supervisor.desktop_snapshot import build_desktop_snapshot
from isotope.features.supervisor.web import create_dashboard_server
from isotope.runtime.in_process import InProcessServer


def test_desktop_snapshot_projects_local_file_read_approval(tmp_path) -> None:
    target = tmp_path / "resume.md"
    target.write_text("resume text\n", encoding="utf-8")
    root = tmp_path / "state"
    api = InProcessServer(root)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="read local file")
    pending = api.submit_action(
        run["run_id"],
        {
            "action": "call_tool",
            "tool": "local_file_read",
            "path": str(target),
            "max_excerpt_chars": 123,
            "summary": "Read one approved local file",
        },
        requires_approval=True,
    )

    snapshot = build_desktop_snapshot(state_root=root)

    approval = next(item for item in snapshot["approvals"] if item["id"] == pending["approval_id"])
    assert approval["title"] == "读取本地文件"
    assert approval["requestedActionSummary"] == {
        "tool": "local_file_read",
        "path": str(target),
        "max_excerpt_chars": 123,
        "scope": "local_file",
    }


def test_desktop_approval_resolve_payload_includes_local_file_read_result(tmp_path) -> None:
    target = tmp_path / "resume.md"
    target.write_text("resume body", encoding="utf-8")
    root = tmp_path / "state"
    api = InProcessServer(root)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="read local file")
    pending = api.submit_action(
        run["run_id"],
        {
            "action": "call_tool",
            "tool": "local_file_read",
            "path": str(target),
            "max_excerpt_chars": 2000,
            "summary": "Read one approved local file",
        },
        requires_approval=True,
    )
    server = create_dashboard_server(
        codex_home=root,
        host="127.0.0.1",
        port=0,
        limit=5,
        stale_after_seconds=999999,
        active_within_seconds=180,
    )
    try:
        payload = server.resolve_desktop_approval_payload(
            pending["approval_id"],
            resolution="approved",
            reason="approve local file read",
            resolver="pytest",
        )
    finally:
        server.server_close()

    assert payload["readResult"]["scope"] == "local_file"
    assert payload["readResult"]["path"] == str(target)
    assert payload["readResult"]["excerpt"] == "resume body"
    assert payload["snapshot"]["counts"]["approvals"] == 0
