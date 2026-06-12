from __future__ import annotations

import http.client
import json
import threading

from isotope.features.supervisor.web import create_dashboard_server


def test_agent_workspace_http_creates_channel_adds_member_and_stops(tmp_path):
    server = create_dashboard_server(
        codex_home=tmp_path / ".codex",
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
        workspaces = _request_json(host, port, "GET", "/desktop/agent-workspaces")
        workspace_id = workspaces["workspaces"][0]["workspace_id"]
        workspace_settings = _request_json(
            host,
            port,
            "POST",
            f"/desktop/agent-workspaces/{workspace_id}",
            {
                "title": "RNA 工作区",
                "root_path": str(tmp_path / "AI_Camp_RNA_2026"),
            },
        )
        channel = _request_json(
            host,
            port,
            "POST",
            f"/desktop/agent-workspaces/{workspace_id}/channels",
            {"name": "rna-research", "topic": "Research direction"},
        )
        channel_id = channel["channel"]["channel_id"]
        member = _request_json(
            host,
            port,
            "POST",
            f"/desktop/agent-workspaces/{workspace_id}/channels/{channel_id}/members",
            {
                "display_name": "Research Codex",
                "role": "Explore RNA strategy.",
                "goal": "Find research directions.",
                "send_policy": "confirm",
                "resume_session_id": "session_research",
            },
        )
        updated = _request_json(
            host,
            port,
            "POST",
            f"/desktop/agent-workspaces/{workspace_id}/channels/{channel_id}/members/"
            f"{member['member']['member_id']}",
            {"action": "update", "send_policy": "draft_only"},
        )
        message = _request_json(
            host,
            port,
            "POST",
            f"/desktop/agent-workspaces/{workspace_id}/conversations/{channel_id}/chat",
            {"message": "sync lanes", "mode": "queue"},
        )
        stop = _request_json(
            host,
            port,
            "POST",
            f"/desktop/agent-workspaces/{workspace_id}/conversations/{channel_id}/control",
            {
                "intent": "terminate",
                "target": "member",
                "target_member_id": member["member"]["member_id"],
                "reason": "User pressed member Stop.",
            },
        )
        removed = _request_json(
            host,
            port,
            "POST",
            f"/desktop/agent-workspaces/{workspace_id}/channels/{channel_id}/members/"
            f"{member['member']['member_id']}",
            {"action": "remove"},
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert workspace_settings["workspace"]["title"] == "RNA 工作区"
    assert workspace_settings["workspace"]["root_path"] == str(
        tmp_path / "AI_Camp_RNA_2026"
    )
    assert channel["channel"]["name"] == "rna-research"
    assert member["member"]["send_policy"] == "confirm"
    assert updated["member"]["send_policy"] == "draft_only"
    assert message["message"]["summary"] == "sync lanes"
    assert stop["control"]["target_member_id"] == member["member"]["member_id"]
    assert removed["member"]["status"] == "archived"


def test_agent_workspace_http_streams_workspace_updates(tmp_path):
    server = create_dashboard_server(
        codex_home=tmp_path / ".codex",
        host="127.0.0.1",
        port=0,
        limit=5,
        stale_after_seconds=999999,
        active_within_seconds=180,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    conn = http.client.HTTPConnection(host, port, timeout=5)
    try:
        workspaces = _request_json(host, port, "GET", "/desktop/agent-workspaces")
        workspace_id = workspaces["workspaces"][0]["workspace_id"]
        conn.request("GET", f"/desktop/agent-workspaces/{workspace_id}/events")
        response = conn.getresponse()
        events = _read_sse_events(response, count=2)
    finally:
        conn.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert response.status == 200
    assert response.getheader("content-type") == "text/event-stream; charset=utf-8"
    assert events[0]["event"] == "ready"
    assert events[1]["event"] == "workspace_update"
    payload = json.loads(events[1]["data"])
    assert payload["workspace"]["workspace_id"] == workspace_id


def _request_json(
    host: str,
    port: int,
    method: str,
    path: str,
    payload: dict | None = None,
) -> dict:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"content-type": "application/json"} if payload is not None else {}
    conn = http.client.HTTPConnection(host, port, timeout=5)
    conn.request(method, path, body=body, headers=headers)
    response = conn.getresponse()
    raw = response.read().decode("utf-8")
    assert response.status < 400, raw
    return json.loads(raw)


def _read_sse_events(response: http.client.HTTPResponse, *, count: int) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    current: dict[str, str] = {}
    while len(events) < count:
        raw = response.readline()
        assert raw, f"stream closed before {count} SSE events"
        line = raw.decode("utf-8").rstrip("\r\n")
        if not line:
            if current:
                events.append(current)
                current = {}
            continue
        if line.startswith("event: "):
            current["event"] = line[len("event: ") :]
        elif line.startswith("data: "):
            current["data"] = current.get("data", "") + line[len("data: ") :]
    return events
