from __future__ import annotations

import json
import os

import pytest

from isotope import artifact_store, codex_live_smoke, codex_task
from isotope.platform.schemas.refs import ResourceRef


class FakeCodexBackend:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def run(self, request):
        self.calls.append(request)
        return self.result


def _codex_result(*, status: str = "completed", content: str = "codex smoke transcript"):
    return codex_task.CodexTaskResult(
        adapter_session_id="codex_live_smoke_session",
        status=status,
        started_at="2026-05-11T00:00:00Z",
        finished_at="2026-05-11T00:00:01Z",
        summary=f"codex live smoke {status}",
        output_artifacts=[
            codex_task.CodexTaskOutputArtifact(
                artifact_type="codex_task_transcript",
                summary="codex live smoke transcript captured",
                content=content,
            )
        ],
        reason_code=f"codex_live_smoke_{status}",
        retryable=False,
        resource_usage={"duration_ms": 1000, "exit_code": 0},
    )


def _transcript(*, stdout: str = "", stderr: str = "", exit_code=None) -> str:
    return json.dumps(
        {
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
            "timeout_seconds": 15,
            "duration_ms": 15000,
            "truncated": False,
        }
    )


def test_codex_live_smoke_is_skipped_by_default_without_artifacts(tmp_path):
    result = codex_live_smoke.run_codex_live_smoke(tmp_path)

    assert result == {
        "status": "skipped",
        "reason_code": "codex_live_smoke_not_enabled",
        "artifact_count": 0,
        "artifact_refs": [],
    }
    assert not (tmp_path / "runs").exists()


def test_codex_live_smoke_accepts_backend_result_into_artifact(tmp_path):
    backend = FakeCodexBackend(_codex_result(content="codex-secret-transcript"))

    result = codex_live_smoke.run_codex_live_smoke(
        tmp_path,
        config=codex_live_smoke.CodexLiveSmokeConfig(enabled=True),
        backend=backend,
    )

    assert result["status"] == "completed"
    assert result["reason_code"] == "codex_live_smoke_completed"
    assert result["artifact_count"] == 1
    ref = ResourceRef(**result["artifact_refs"][0])
    assert artifact_store.ArtifactStore(tmp_path).get_content(ref) == "codex-secret-transcript"
    assert backend.calls[0].workspace_binding["mode"] == "shared_ro"
    assert backend.calls[0].grants["tools"] == ["codex_task"]
    assert backend.calls[0].grants["workspace"] == {"mode": "shared_ro"}


def test_codex_live_smoke_result_does_not_expose_prompt_or_transcript(tmp_path):
    prompt = "PROMPT_SHOULD_NOT_LEAK"
    transcript = "TRANSCRIPT_SHOULD_NOT_LEAK"
    backend = FakeCodexBackend(_codex_result(content=transcript))

    result = codex_live_smoke.run_codex_live_smoke(
        tmp_path,
        config=codex_live_smoke.CodexLiveSmokeConfig(enabled=True, prompt=prompt),
        backend=backend,
    )

    assert prompt not in repr(result)
    assert transcript not in repr(result)


def test_codex_live_smoke_diagnoses_network_unreachable_without_leaking_transcript(tmp_path):
    network_error = "Network unreachable (os error 101)"
    backend = FakeCodexBackend(
        _codex_result(
            status="timeout",
            content=_transcript(stderr=f"failed to connect to websocket: {network_error}"),
        )
    )

    result = codex_live_smoke.diagnose_codex_live_smoke(
        tmp_path,
        config=codex_live_smoke.CodexLiveSmokeConfig(enabled=True),
        backend=backend,
    )

    assert result["diagnosis"] == {
        "category": "network_unreachable",
        "process_started": True,
        "artifact_captured": True,
        "summary": "local codex started but could not reach the service",
        "next_step": "check proxy or network settings before product wiring",
    }
    assert network_error not in repr(result)


def test_codex_live_smoke_diagnoses_auth_failure_without_leaking_transcript(tmp_path):
    auth_error = "401 Unauthorized: login required"
    backend = FakeCodexBackend(
        _codex_result(
            status="failed",
            content=_transcript(stderr=auth_error, exit_code=1),
        )
    )

    result = codex_live_smoke.diagnose_codex_live_smoke(
        tmp_path,
        config=codex_live_smoke.CodexLiveSmokeConfig(enabled=True),
        backend=backend,
    )

    assert result["diagnosis"]["category"] == "auth_unavailable"
    assert result["diagnosis"]["process_started"] is True
    assert result["diagnosis"]["artifact_captured"] is True
    assert auth_error not in repr(result)


@pytest.mark.skipif(
    os.environ.get("ISOTOPE_RUN_LIVE_CODEX_SMOKE") != "1",
    reason="live Codex smoke is opt-in",
)
def test_live_codex_cli_smoke_records_real_process_artifact(tmp_path):
    result = codex_live_smoke.run_codex_live_smoke(
        tmp_path,
        config=codex_live_smoke.CodexLiveSmokeConfig(enabled=True, timeout_seconds=45),
    )

    assert result["status"] in {"completed", "failed", "timeout", "not_configured"}
    if result["status"] == "not_configured":
        assert result["reason_code"] == "codex_task_adapter_not_configured"
    else:
        assert result["artifact_count"] == 1
        ref = ResourceRef(**result["artifact_refs"][0])
        content = artifact_store.ArtifactStore(tmp_path).get_content(ref)
        assert content
        assert "exit_code" in content
