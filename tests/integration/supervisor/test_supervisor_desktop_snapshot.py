from __future__ import annotations

import http.client
import json
import threading

from isotope.features.supervisor.desktop_snapshot import (
    _low_sensitive_preview,
    build_desktop_snapshot,
)
from isotope.features.supervisor.planner.goal_queue import record_supervisor_goal
from isotope.features.supervisor.web import create_dashboard_server


def test_desktop_snapshot_empty_root_uses_contract_shape(tmp_path):
    snapshot = build_desktop_snapshot(codex_home=tmp_path)

    assert snapshot["schemaVersion"] == 1
    assert isinstance(snapshot["snapshotId"], str)
    assert snapshot["source"] == {
        "kind": "real",
        "label": "supervisor_state_projection",
        "backendRef": f"codex_home:{tmp_path}",
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
    assert snapshot["activities"][0]["source"]["backendRef"] == f"codex_home:{tmp_path}"
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

    snapshot = build_desktop_snapshot(codex_home=tmp_path)

    assert snapshot["activities"][0]["kind"] == "supervisor"
    assert snapshot["activeActivity"]["id"] == snapshot["activities"][0]["id"]
    assert snapshot["activeGoal"]["title"] == "Ship the desktop MVP"
    goal_node = next(activity for activity in snapshot["activities"] if activity["kind"] == "goal")
    assert goal_node["title"] == "Ship the desktop MVP"
    assert goal_node["parentId"] == snapshot["activities"][0]["id"]
    assert snapshot["activeGoal"]["id"] == goal_node["sourceRef"]["id"]
    assert goal_node["source"]["kind"] == "derived"
    assert goal_node["source"]["sourceRef"]["kind"] == "goal"


def test_desktop_snapshot_redacts_long_or_secret_preview_content(tmp_path):
    snapshot = build_desktop_snapshot(codex_home=tmp_path)

    serialized = str(snapshot).lower()

    assert "sk-test-secret" not in serialized
    assert "token=" not in serialized
    assert "x" * 2200 not in serialized


def test_low_sensitive_preview_guard_rejects_secrets_and_long_content():
    assert _low_sensitive_preview("Short status summary.") == "Short status summary."
    assert _low_sensitive_preview("token=sk-test-secret") is None
    assert _low_sensitive_preview("x" * 2200) is None


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
    assert payload["schemaVersion"] == 1
    assert payload["source"]["kind"] == "real"
