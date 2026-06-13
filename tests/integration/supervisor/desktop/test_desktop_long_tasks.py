from __future__ import annotations

import http.client
import json
import threading

from isotope.features.supervisor.web import create_dashboard_server


def test_desktop_long_task_endpoints_create_status_and_control(tmp_path):
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
            "/desktop/long-tasks",
            body=json.dumps({"goal": "Run desktop long task."}),
            headers={"content-type": "application/json"},
        )
        create_response = conn.getresponse()
        create_payload = json.loads(create_response.read().decode("utf-8"))
        task_id = create_payload["task"]["task_id"]

        conn.request("GET", f"/desktop/long-tasks/{task_id}")
        status_response = conn.getresponse()
        status_payload = json.loads(status_response.read().decode("utf-8"))

        conn.request(
            "POST",
            f"/desktop/long-tasks/{task_id}/control",
            body=json.dumps({"control": "pause", "reason": "Need operator review."}),
            headers={"content-type": "application/json"},
        )
        control_response = conn.getresponse()
        control_payload = json.loads(control_response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert create_response.status == 200
    assert status_response.status == 200
    assert control_response.status == 200
    assert create_payload["status"] == "ok"
    assert status_payload["task"]["task_id"] == task_id
    assert control_payload["task"]["status"] == "paused"
    assert control_payload["task"]["control_reason"] == "Need operator review."
