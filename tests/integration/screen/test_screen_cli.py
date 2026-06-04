from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from isotope.workspace.artifacts import ArtifactStore


REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = REPO_ROOT / "src"


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "isotope.features.screen.runner", *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )


def test_screen_cli_inspect_returns_screen_artifact_json(tmp_path):
    store = ArtifactStore(tmp_path)
    artifact = store.create_artifact(
        "run_001",
        execution_id="exec_001",
        artifact_type="screen_metadata",
        summary="screen metadata captured",
        content=json.dumps({"target": {"app": "notepad.exe"}}, sort_keys=True),
    )

    result = _run_cli(
        "inspect",
        "--root",
        str(tmp_path),
        "--run-id",
        "run_001",
        "--artifact-id",
        artifact.artifact_id,
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["artifact"]["artifact_type"] == "screen_metadata"
    assert payload["artifact"]["ref"] == artifact.ref.to_dict()
    assert payload["content"]["target"]["app"] == "notepad.exe"


def test_screen_cli_inspect_rejects_non_screen_artifact(tmp_path):
    store = ArtifactStore(tmp_path)
    artifact = store.create_artifact(
        "run_001",
        execution_id="exec_001",
        artifact_type="research.report",
        summary="not screen",
        content="{}",
    )

    result = _run_cli(
        "inspect",
        "--root",
        str(tmp_path),
        "--run-id",
        "run_001",
        "--artifact-id",
        artifact.artifact_id,
        "--json",
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "screen_runner_error"
    assert payload["error"]["message"] == "artifact is not a screen artifact"


def test_screen_cli_report_summarizes_metadata_only_observe(tmp_path):
    store = ArtifactStore(tmp_path)
    metadata = store.create_artifact(
        "run_001",
        execution_id="exec_001",
        artifact_type="screen_metadata",
        summary="screen metadata captured",
        content=json.dumps(
            {
                "target": {
                    "window_id": "123",
                    "title": "Notes",
                    "app": "notepad.exe",
                    "is_minimized": True,
                },
                "matched_count": 3,
                "selected_window_id": "123",
                "selection_reason": "first_match",
            },
            sort_keys=True,
        ),
    )
    diagnostic = store.create_artifact(
        "run_001",
        execution_id="exec_001",
        artifact_type="screen_diagnostic",
        summary="screen screenshot diagnostic",
        content=json.dumps(
            {
                "reason_code": "screen_screenshot_unavailable",
                "recovery": "restore_window_requires_approval",
            },
            sort_keys=True,
        ),
    )

    result = _run_cli("report", "--root", str(tmp_path), "--run-id", "run_001", "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["summary"]["observe_status"] == "metadata_only"
    assert payload["summary"]["screenshot_available"] is False
    assert payload["summary"]["target"]["is_minimized"] is True
    assert payload["summary"]["matched_count"] == 3
    assert payload["summary"]["selection_reason"] == "first_match"
    assert payload["summary"]["recovery_actions"] == ["restore_window_requires_approval"]
    assert [artifact["artifact_id"] for artifact in payload["artifacts"]] == [
        metadata.artifact_id,
        diagnostic.artifact_id,
    ]


def test_screen_cli_report_plain_output_is_public_metadata(tmp_path):
    store = ArtifactStore(tmp_path)
    store.create_artifact(
        "run_001",
        execution_id="exec_001",
        artifact_type="screen_diagnostic",
        summary="screen screenshot diagnostic",
        content=json.dumps(
            {
                "reason_code": "screen_screenshot_unavailable",
                "message": "raw backend stack should not print in report",
                "recovery": "restore_window_requires_approval",
            },
            sort_keys=True,
        ),
    )

    result = _run_cli("report", "--root", str(tmp_path), "--run-id", "run_001")

    assert result.returncode == 0, result.stderr
    assert "status: ok" in result.stdout
    assert "observe: metadata_only" in result.stdout
    assert "screenshot: unavailable" in result.stdout
    assert "recovery: restore_window_requires_approval" in result.stdout
    assert "raw backend stack" not in result.stdout


def test_screen_cli_report_summarizes_control_plan(tmp_path):
    store = ArtifactStore(tmp_path)
    plan = store.create_artifact(
        "run_001",
        execution_id="exec_001",
        artifact_type="screen_control_plan",
        summary="screen control result",
        content=json.dumps(
            {
                "action_count": 2,
                "executed": False,
                "planned_actions": ["restore_window", "click"],
            },
            sort_keys=True,
        ),
    )

    result = _run_cli("report", "--root", str(tmp_path), "--run-id", "run_001", "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["summary"]["control_status"] == "planned"
    assert payload["summary"]["control_plan_count"] == 1
    assert payload["summary"]["control_result_count"] == 0
    assert payload["summary"]["approval_required"] is True
    assert payload["summary"]["interferes_with_screen"] is True
    assert payload["summary"]["control_actions"] == [
        {
            "artifact_id": plan.artifact_id,
            "action_count": 2,
            "executed": False,
            "action_types": ["restore_window", "click"],
        }
    ]


def test_screen_cli_report_plain_output_summarizes_control_plan(tmp_path):
    store = ArtifactStore(tmp_path)
    store.create_artifact(
        "run_001",
        execution_id="exec_001",
        artifact_type="screen_control_plan",
        summary="screen control result",
        content=json.dumps(
            {
                "action_count": 1,
                "executed": False,
                "planned_actions": ["restore_window"],
                "private_note": "raw control payload should not print",
            },
            sort_keys=True,
        ),
    )

    result = _run_cli("report", "--root", str(tmp_path), "--run-id", "run_001")

    assert result.returncode == 0, result.stderr
    assert "control: planned" in result.stdout
    assert "approval: required" in result.stdout
    assert "interference: true" in result.stdout
    assert "action: restore_window count=1 executed=false" in result.stdout
    assert "raw control payload" not in result.stdout


def test_screen_cli_real_smoke_plan_carries_allowlist_file(tmp_path):
    allowlist_file = tmp_path / "screen-allowlist.json"
    allowlist_file.write_text(
        json.dumps({"allowed_apps": ["notepad.exe"]}, sort_keys=True),
        encoding="utf-8",
    )

    result = _run_cli(
        "real-smoke-plan",
        "--root",
        str(tmp_path),
        "--app",
        "notepad.exe",
        "--allowlist-file",
        str(allowlist_file),
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert all(
        f"--allowlist-file {allowlist_file}" in command
        for command in payload["commands"]
    )


def test_screen_cli_real_smoke_plan_carries_allowlist_profile(tmp_path):
    profile_dir = tmp_path / "profiles"
    profile_dir.mkdir()
    profile_file = profile_dir / "mahjong.json"
    profile_file.write_text(
        json.dumps({"allowed_title_contains": ["Mahjong Soul"]}, sort_keys=True),
        encoding="utf-8",
    )

    result = _run_cli(
        "real-smoke-plan",
        "--root",
        str(tmp_path),
        "--app",
        "msedge.exe",
        "--allowlist-profile",
        "mahjong",
        "--allowlist-profile-dir",
        str(profile_dir),
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert all("--allowlist-profile mahjong" in command for command in payload["commands"])
    assert all(
        f"--allowlist-profile-dir {profile_dir}" in command
        for command in payload["commands"]
    )


def test_screen_cli_allowlist_validate_returns_public_metadata_json(tmp_path):
    allowlist_file = tmp_path / "screen-allowlist.json"
    allowlist_file.write_text(
        json.dumps(
            {
                "allowed_apps": ["notepad.exe"],
                "allowed_title_contains": ["Mahjong Soul"],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    result = _run_cli(
        "allowlist",
        "validate",
        "--path",
        str(allowlist_file),
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload == {
        "status": "ok",
        "path": str(allowlist_file),
        "allowed_app_count": 1,
        "allowed_title_contains_count": 1,
        "allow_first_match_execute": False,
    }


def test_screen_cli_allowlist_validate_profile_returns_public_metadata_json(tmp_path):
    profile_dir = tmp_path / "profiles"
    profile_dir.mkdir()
    profile_file = profile_dir / "mahjong.json"
    profile_file.write_text(
        json.dumps(
            {
                "allowed_apps": ["msedge.exe"],
                "allowed_title_contains": ["private game title"],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    result = _run_cli(
        "allowlist",
        "validate",
        "--profile",
        "mahjong",
        "--profile-dir",
        str(profile_dir),
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload == {
        "status": "ok",
        "profile": "mahjong",
        "path": str(profile_file),
        "allowed_app_count": 1,
        "allowed_title_contains_count": 1,
        "allow_first_match_execute": False,
    }
    assert "private game title" not in result.stdout


def test_screen_cli_allowlist_validate_plain_output_is_public_metadata(tmp_path):
    allowlist_file = tmp_path / "screen-allowlist.json"
    allowlist_file.write_text(
        json.dumps(
            {
                "allowed_apps": ["notepad.exe"],
                "allowed_title_contains": ["private window title fragment"],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    result = _run_cli("allowlist", "validate", "--path", str(allowlist_file))

    assert result.returncode == 0, result.stderr
    assert "status: ok" in result.stdout
    assert "allowed_apps: 1" in result.stdout
    assert "allowed_title_contains: 1" in result.stdout
    assert "allow_first_match_execute: false" in result.stdout
    assert "private window title fragment" not in result.stdout


def test_screen_cli_allowlist_validate_profile_plain_output_is_public_metadata(tmp_path):
    profile_dir = tmp_path / "profiles"
    profile_dir.mkdir()
    (profile_dir / "mahjong.json").write_text(
        json.dumps(
            {
                "allowed_apps": ["msedge.exe"],
                "allowed_title_contains": ["private game title"],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    result = _run_cli(
        "allowlist",
        "validate",
        "--profile",
        "mahjong",
        "--profile-dir",
        str(profile_dir),
    )

    assert result.returncode == 0, result.stderr
    assert "status: ok" in result.stdout
    assert "profile: mahjong" in result.stdout
    assert "allowed_apps: 1" in result.stdout
    assert "allowed_title_contains: 1" in result.stdout
    assert "private game title" not in result.stdout


def test_screen_cli_allowlist_validate_rejects_malformed_json(tmp_path):
    allowlist_file = tmp_path / "screen-allowlist.json"
    allowlist_file.write_text(
        json.dumps({"allowed_apps": "not-a-list"}, sort_keys=True),
        encoding="utf-8",
    )

    result = _run_cli(
        "allowlist",
        "validate",
        "--path",
        str(allowlist_file),
        "--json",
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "screen_runner_error"
    assert payload["error"]["message"] == (
        "allowlist-file.allowed_apps must be a list of strings"
    )


def test_screen_cli_allowlist_list_returns_public_metadata_json(tmp_path):
    profile_dir = tmp_path / "profiles"
    profile_dir.mkdir()
    (profile_dir / "mahjong.json").write_text(
        json.dumps(
            {
                "allowed_apps": ["msedge.exe"],
                "allowed_title_contains": ["private game title"],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (profile_dir / "notes.json").write_text(
        json.dumps({"allowed_apps": ["notepad.exe"]}, sort_keys=True),
        encoding="utf-8",
    )

    result = _run_cli(
        "allowlist",
        "list",
        "--profile-dir",
        str(profile_dir),
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload == {
        "status": "ok",
        "profile_dir": str(profile_dir),
        "profile_count": 2,
        "profiles": [
            {
                "profile": "mahjong",
                "path": str(profile_dir / "mahjong.json"),
                "allowed_app_count": 1,
                "allowed_title_contains_count": 1,
                "allow_first_match_execute": False,
            },
            {
                "profile": "notes",
                "path": str(profile_dir / "notes.json"),
                "allowed_app_count": 1,
                "allowed_title_contains_count": 0,
                "allow_first_match_execute": False,
            },
        ],
    }
    assert "private game title" not in result.stdout


def test_screen_cli_allowlist_list_plain_output_is_public_metadata(tmp_path):
    profile_dir = tmp_path / "profiles"
    profile_dir.mkdir()
    (profile_dir / "mahjong.json").write_text(
        json.dumps(
            {
                "allowed_apps": ["msedge.exe"],
                "allowed_title_contains": ["private game title"],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    result = _run_cli("allowlist", "list", "--profile-dir", str(profile_dir))

    assert result.returncode == 0, result.stderr
    assert "status: ok" in result.stdout
    assert "profile_dir:" in result.stdout
    assert "profile_count: 1" in result.stdout
    assert "profile: mahjong allowed_apps=1 allowed_title_contains=1" in result.stdout
    assert "private game title" not in result.stdout


def test_screen_cli_allowlist_template_returns_editable_json():
    result = _run_cli("allowlist", "template", "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload == {
        "allowed_apps": ["notepad.exe"],
        "allowed_title_contains": ["Untitled - Notepad"],
    }
    assert "allow_first_match_execute" not in payload


def test_screen_cli_allowlist_template_plain_output_is_json():
    result = _run_cli("allowlist", "template")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["allowed_apps"] == ["notepad.exe"]
    assert payload["allowed_title_contains"] == ["Untitled - Notepad"]
