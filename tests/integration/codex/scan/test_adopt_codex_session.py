from __future__ import annotations

import json

import pytest

from ..helpers import NOW, _assistant_message, _user_message, _write_session
from isotope.features.supervisor.flow import CodexSupervisorFlow, render_plain_report
from isotope.features.supervisor.registry import (
    adopt_codex_session,
    read_managed_records,
)
from isotope.features.supervisor.registry.records import default_registry_path


SESSION_ID = "019e9830-8a72-7ff1-8b2e-310b9d66372b"


def test_adopt_codex_session_records_resume_identity(tmp_path):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_session(
        codex_home,
        "2026/06/05/rollout-session.jsonl",
        session_id=SESSION_ID,
        cwd=str(workspace),
        events=[_assistant_message("2026-06-05T15:20:00Z", "继续科研探索。")],
    )

    record = adopt_codex_session(
        codex_home=codex_home,
        name="research",
        session_id=SESSION_ID,
        prompt="接管已有科研会话",
        now=lambda: NOW,
    )

    assert record.name == "research"
    assert record.cwd == str(workspace)
    assert record.backend == "codex_session"
    assert record.resume_session_id == SESSION_ID
    assert record.pid == 0
    records = read_managed_records(default_registry_path(codex_home))
    assert records == (record,)


def test_adopt_codex_session_rejects_unknown_session(tmp_path):
    codex_home = tmp_path / ".codex"

    with pytest.raises(ValueError, match="Codex session not found"):
        adopt_codex_session(
            codex_home=codex_home,
            name="research",
            session_id=SESSION_ID,
            prompt="接管已有科研会话",
        )


def test_adopt_codex_session_requires_cwd_when_session_has_no_cwd(tmp_path):
    codex_home = tmp_path / ".codex"
    _write_session(
        codex_home,
        "2026/06/05/rollout-session.jsonl",
        session_id=SESSION_ID,
        cwd="",
        events=[_assistant_message("2026-06-05T15:20:00Z", "继续科研探索。")],
    )

    with pytest.raises(ValueError, match="cwd is required"):
        adopt_codex_session(
            codex_home=codex_home,
            name="research",
            session_id=SESSION_ID,
            prompt="接管已有科研会话",
        )


def test_scan_projects_adopted_codex_session_from_resume_identity(tmp_path):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_session(
        codex_home,
        "2026/06/05/rollout-session.jsonl",
        session_id=SESSION_ID,
        cwd=str(workspace),
        events=[
            _user_message("2026-06-05T15:15:00Z", "先开始科研探索"),
            _assistant_message("2026-06-05T15:20:00Z", "继续科研探索。"),
        ],
    )
    adopt_codex_session(
        codex_home=codex_home,
        name="research",
        session_id=SESSION_ID,
        prompt="接管已有科研会话",
        now=lambda: NOW,
    )

    report = CodexSupervisorFlow(
        codex_home=codex_home,
        now=lambda: NOW,
    ).scan(limit=5)

    managed = next(session for session in report.sessions if session.managed)
    assert managed.session_id.startswith("managed:")
    assert managed.managed_name == "research"
    assert managed.managed_backend == "codex_session"
    assert managed.managed_resume_session_id == SESSION_ID
    assert managed.status == "working"
    text = render_plain_report(report)
    assert "托管：research backend=codex_session" in text


def test_adopt_codex_session_cli_json(capsys, tmp_path, monkeypatch):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_session(
        codex_home,
        "2026/06/05/rollout-session.jsonl",
        session_id=SESSION_ID,
        cwd=str(workspace),
        events=[_assistant_message("2026-06-05T15:20:00Z", "继续科研探索。")],
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    from isotope.features.supervisor.runner import main as supervisor_main

    exit_code = supervisor_main(
        [
            "adopt",
            "--codex-home",
            str(codex_home),
            "--name",
            "research",
            "--session-id",
            SESSION_ID,
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["managed"]["backend"] == "codex_session"
    assert payload["managed"]["resume_session_id"] == SESSION_ID
