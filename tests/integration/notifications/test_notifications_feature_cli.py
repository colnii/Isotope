from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = REPO_ROOT / "src"

FORBIDDEN_CONTENT_KEYS = {
    "content",
    "artifact_content",
    "full_content",
    "full_text",
    "raw_content",
    "raw_artifact_content",
    "text",
}


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "isotope.features.notifications.runner", *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )


def _assert_public_metadata(value: Any) -> None:
    if isinstance(value, dict):
        assert FORBIDDEN_CONTENT_KEYS.isdisjoint(value)
        for nested in value.values():
            _assert_public_metadata(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_public_metadata(nested)


def test_notification_cli_creates_lists_and_marks_read_as_json(tmp_path):
    create_result = _run_cli(
        "create",
        "--root",
        str(tmp_path),
        "--type",
        "approval",
        "--title",
        "Worker needs approval",
        "--source-ref-json",
        json.dumps(
            {
                "ref_type": "supervisor_worker",
                "worker": {"name": "worker-a"},
            }
        ),
        "--json",
    )

    assert create_result.returncode == 0, create_result.stderr
    created_payload = json.loads(create_result.stdout)
    notification = created_payload["notification"]
    notification_id = notification["notification_id"]
    assert created_payload["status"] == "ok"
    assert notification["type"] == "approval"
    assert notification["title"] == "Worker needs approval"
    assert notification["unread"] is True
    assert notification["source_ref"] == {
        "ref_type": "supervisor_worker",
        "worker": {"name": "worker-a"},
    }

    unread_result = _run_cli("list", "--root", str(tmp_path), "--unread", "--json")
    type_result = _run_cli("list", "--root", str(tmp_path), "--type", "approval", "--json")
    mark_result = _run_cli("mark-read", "--root", str(tmp_path), "--notification-id", notification_id, "--json")
    read_result = _run_cli("list", "--root", str(tmp_path), "--read", "--json")

    assert unread_result.returncode == 0, unread_result.stderr
    assert type_result.returncode == 0, type_result.stderr
    assert mark_result.returncode == 0, mark_result.stderr
    assert read_result.returncode == 0, read_result.stderr
    assert json.loads(unread_result.stdout) == {"status": "ok", "notifications": [notification]}
    assert json.loads(type_result.stdout) == {"status": "ok", "notifications": [notification]}
    marked = json.loads(mark_result.stdout)["notification"]
    assert marked["notification_id"] == notification_id
    assert marked["unread"] is False
    assert marked["read_at"] is not None
    assert json.loads(read_result.stdout) == {"status": "ok", "notifications": [marked]}
    _assert_public_metadata(json.loads(read_result.stdout))


def test_notification_cli_rejects_conflicting_read_filters(tmp_path):
    result = _run_cli("list", "--root", str(tmp_path), "--unread", "--read", "--json")

    assert result.returncode == 2
    assert json.loads(result.stdout) == {
        "status": "error",
        "error": {
            "code": "notification_runner_error",
            "message": "list cannot combine --unread and --read",
        },
    }


def test_notification_cli_rejects_sensitive_source_ref_json(tmp_path):
    result = _run_cli(
        "create",
        "--root",
        str(tmp_path),
        "--type",
        "approval",
        "--title",
        "Worker needs approval",
        "--source-ref-json",
        '{"ref_type": "artifact", "raw_content": "secret"}',
        "--json",
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "notification_runner_error"
    assert payload["error"]["message"] == "source_ref must stay public"
