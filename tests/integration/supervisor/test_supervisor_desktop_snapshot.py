from __future__ import annotations

import http.client
import json
import threading

import isotope.runtime.in_process as runtime
from isotope.features.supervisor.desktop_snapshot import (
    _public_metadata_preview,
    build_desktop_snapshot,
)
from isotope.features.supervisor.planner.decision_requests import record_decision_request
from isotope.features.supervisor.planner.goal_queue import (
    record_supervisor_goal,
    record_supervisor_goal_status,
)
from isotope.features.supervisor.web import create_dashboard_server
from isotope.workspace.artifacts import ArtifactStore


def _terminal_intent(argv: list[str]) -> dict:
    return {
        "action": "call_tool",
        "tool": "terminal_exec",
        "argv": argv,
        "summary": "terminal command",
    }


def test_desktop_snapshot_empty_root_uses_contract_shape(tmp_path):
    snapshot = build_desktop_snapshot(state_root=tmp_path)

    assert snapshot["schemaVersion"] == 1
    assert isinstance(snapshot["snapshotId"], str)
    assert snapshot["source"] == {
        "kind": "real",
        "label": "supervisor_state_projection",
        "backendRef": f"supervisor_state:{tmp_path}",
    }
    assert snapshot["counts"] == {
        "runningAgents": 0,
        "needsAttention": 0,
        "approvals": 0,
        "artifacts": 0,
        "errors": 0,
    }
    assert snapshot["activeAgent"]["kind"] == "supervisor"
    assert snapshot["activeAgent"]["source"]["kind"] == "real"
    assert snapshot["agents"][0]["kind"] == "supervisor"
    assert snapshot["activities"][0]["kind"] == "supervisor"
    assert snapshot["activities"][0]["summary"] == "Supervisor 状态投影已连接。"
    assert (
        snapshot["activities"][0]["source"]["backendRef"]
        == f"supervisor_state:{tmp_path}"
    )
    assert set(snapshot["activeActivity"]) == {"id", "kind", "title", "status", "source"}
    assert "activeGoal" not in snapshot
    assert "eventCursor" not in snapshot
    assert "lastEventId" not in snapshot
    assert snapshot["approvals"] == []
    assert snapshot["artifacts"] == []
    assert snapshot["runningToolCalls"] == []


def test_desktop_snapshot_maps_active_goal_to_activity(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    record_supervisor_goal(
        codex_home=tmp_path,
        goal="Ship the desktop MVP",
        cwd=workspace,
        target_name="desktop-mvp",
        depends_on=(),
        stage="frontend",
        scope="desktop",
        merge_gate="manual",
    )

    snapshot = build_desktop_snapshot(state_root=tmp_path)

    assert snapshot["activities"][0]["kind"] == "supervisor"
    assert snapshot["activities"][0]["status"] == "running"
    assert snapshot["activeActivity"]["status"] == "running"
    assert snapshot["activeAgent"]["status"] == "running"
    assert snapshot["counts"]["runningAgents"] == 1
    assert snapshot["activeActivity"]["id"] == snapshot["activities"][0]["id"]
    assert set(snapshot["activeActivity"]) == {"id", "kind", "title", "status", "source"}
    assert snapshot["activeGoal"]["title"] == "Ship the desktop MVP"
    assert "kind" not in snapshot["activeGoal"]
    goal_node = next(activity for activity in snapshot["activities"] if activity["kind"] == "goal")
    assert goal_node["title"] == "Ship the desktop MVP"
    assert goal_node["parentId"] == snapshot["activities"][0]["id"]
    assert snapshot["activeGoal"]["id"] == goal_node["sourceRef"]["id"]
    assert goal_node["source"]["kind"] == "derived"
    assert goal_node["source"]["sourceRef"]["kind"] == "goal"


def test_desktop_snapshot_redacts_long_or_secret_preview_content(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    goal = record_supervisor_goal(
        codex_home=tmp_path,
        goal="Inspect preview redaction",
        cwd=workspace,
    )
    record_supervisor_goal_status(
        codex_home=tmp_path,
        goal_id=goal.goal_id,
        status="needs_user",
        summary="token=sk-test-secret " + "x" * 2200,
    )

    snapshot = build_desktop_snapshot(state_root=tmp_path)

    serialized = str(snapshot).lower()
    goal_node = next(activity for activity in snapshot["activities"] if activity["kind"] == "goal")

    assert "sk-test-secret" not in serialized
    assert "token=" not in serialized
    assert "x" * 2200 not in serialized
    assert "summary" not in goal_node


def test_desktop_snapshot_maps_active_decision_to_approval_summary(tmp_path):
    record_decision_request(
        codex_home=tmp_path,
        action={
            "session_id": "session-1",
            "question": "Approve launch?",
            "reason": "worker needs confirmation",
            "target_name": "desktop-worker",
            "context_status": "ready",
        },
    )

    snapshot = build_desktop_snapshot(state_root=tmp_path)

    assert snapshot["activeAgent"]["status"] == "needs_attention"
    assert snapshot["activeActivity"]["status"] == "needs_attention"
    assert snapshot["counts"]["approvals"] == 1
    assert snapshot["counts"]["needsAttention"] == 1
    assert snapshot["approvals"] == [
        {
            "id": snapshot["approvals"][0]["id"],
            "title": "Approve launch?",
            "status": "pending",
            "source": {
                "kind": "derived",
                "label": "supervisor_decision_request",
                "sourceRef": {
                    "kind": "approval",
                    "id": snapshot["approvals"][0]["id"],
                    "label": "Approve launch?",
                },
            },
        }
    ]


def test_desktop_snapshot_includes_runtime_pending_approval_without_command_leak(tmp_path):
    api = runtime.InProcessServer(tmp_path)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="approve terminal command")

    pending = api.submit_action(
        run["run_id"],
        _terminal_intent(["bash", "-lc", "printf SHOULD_NOT_LEAK"]),
        requires_approval=True,
    )

    snapshot = build_desktop_snapshot(state_root=tmp_path)

    assert snapshot["counts"]["approvals"] == 1
    assert snapshot["counts"]["needsAttention"] == 1
    approval = snapshot["approvals"][0]
    assert approval["id"] == pending["approval_id"]
    assert approval["runId"] == run["run_id"]
    assert approval["proposalId"] == pending["proposal_id"]
    assert approval["decisionId"] == pending["decision_id"]
    assert approval["status"] == "pending"
    assert approval["title"] == "需要批准 terminal_exec: bash"
    assert approval["source"]["label"] == "runtime_approval_request"
    assert approval["requestedActionSummary"]["tool"] == "terminal_exec"
    assert approval["requestedActionSummary"]["terminal_command"] == "bash"
    assert "SHOULD_NOT_LEAK" not in json.dumps(snapshot, ensure_ascii=False)


def test_public_metadata_preview_guard_rejects_secrets_and_long_content():
    assert _public_metadata_preview("Short status summary.") == "Short status summary."
    assert _public_metadata_preview("token=sk-test-secret") is None
    assert _public_metadata_preview("x" * 2200) is None


def test_desktop_snapshot_endpoint_serves_real_snapshot(tmp_path):
    server = create_dashboard_server(
        codex_home=tmp_path,
        host="127.0.0.1",
        port=0,
        limit=5,
        stale_after_seconds=999999,
        active_within_seconds=180,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request("GET", "/desktop/snapshot")
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert response.status == 200
    assert response.getheader("access-control-allow-origin") == "*"
    assert payload["schemaVersion"] == 1
    assert payload["source"]["kind"] == "real"


def test_desktop_screen_artifact_endpoint_serves_original_screenshot_payload(tmp_path):
    artifact = ArtifactStore(tmp_path).create_artifact(
        "run_screen_001",
        "exec_screen_001",
        "screen_screenshot",
        "screen screenshot captured",
        json.dumps(
            {
                "encoding": "base64",
                "media_type": "image/png",
                "width": 1920,
                "height": 1080,
                "data": "ZmFrZS1mdWxsLXBuZw==",
            },
            sort_keys=True,
        ),
    )
    server = create_dashboard_server(
        codex_home=tmp_path,
        host="127.0.0.1",
        port=0,
        limit=5,
        stale_after_seconds=999999,
        active_within_seconds=180,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request("GET", f"/desktop/artifacts/{artifact.artifact_id}/screen-content")
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert response.status == 200
    assert payload["status"] == "ok"
    assert payload["artifact"]["ref"] == artifact.ref.to_dict()
    assert payload["image"]["mediaType"] == "image/png"
    assert payload["image"]["width"] == 1920
    assert payload["image"]["height"] == 1080
    assert payload["image"]["dataUrl"] == "data:image/png;base64,ZmFrZS1mdWxsLXBuZw=="
    assert payload["image"]["data"] == "ZmFrZS1mdWxsLXBuZw=="
    assert payload["file"]["path"].endswith(f"{artifact.artifact_id}.json")
    assert payload["file"]["directory"].endswith("runs/run_screen_001/artifacts")
    assert payload["file"]["downloadFilename"] == f"{artifact.artifact_id}.png"


def test_desktop_snapshot_endpoint_allows_browser_readiness_check(tmp_path):
    server = create_dashboard_server(
        codex_home=tmp_path,
        host="127.0.0.1",
        port=0,
        limit=5,
        stale_after_seconds=999999,
        active_within_seconds=180,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request(
            "OPTIONS",
            "/desktop/snapshot",
            headers={
                "origin": "http://127.0.0.1:5173",
                "access-control-request-method": "GET",
            },
        )
        response = conn.getresponse()
        response.read()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert response.status == 204
    assert response.getheader("access-control-allow-origin") == "*"
    assert "GET" in response.getheader("access-control-allow-methods")


def test_desktop_approval_resolve_endpoint_approves_runtime_pending_action(tmp_path):
    api = runtime.InProcessServer(tmp_path)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="approve from desktop")
    pending = api.submit_action(
        run["run_id"],
        _terminal_intent(["bash", "-lc", "printf desktop-approved"]),
        requires_approval=True,
    )
    server = create_dashboard_server(
        codex_home=tmp_path,
        host="127.0.0.1",
        port=0,
        limit=5,
        stale_after_seconds=999999,
        active_within_seconds=180,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request(
            "POST",
            f"/desktop/approvals/{pending['approval_id']}/resolve",
            body=json.dumps({"resolution": "approved", "reason": "desktop operator approved"}),
            headers={"content-type": "application/json"},
        )
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert response.status == 200
    assert payload["status"] == "ok"
    assert payload["approvalId"] == pending["approval_id"]
    assert payload["resolution"] == "approved"
    assert payload["runStatus"] == "completed"
    event_types = [event.event_type for event in api.get_events(run["run_id"])]
    assert event_types.index("approval.resolved") < event_types.index("action.started")
    assert payload["snapshot"]["counts"]["approvals"] == 0
