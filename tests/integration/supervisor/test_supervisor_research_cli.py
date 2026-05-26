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
        [sys.executable, "-m", "isotope.features.supervisor.runner", *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )


def test_supervisor_research_command_proxies_research_flow(tmp_path):
    result = _run_cli(
        "research",
        "--root",
        str(tmp_path),
        "--query",
        "agent memory retrieval",
        "--provider",
        "fake",
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["research"]["query"] == "agent memory retrieval"
    assert payload["research"]["provider"] == "fake"
    assert [artifact["artifact_type"] for artifact in payload["artifacts"]] == [
        "research.raw_transcript",
        "research.report",
    ]


def test_supervisor_research_providers_proxies_registry_json(tmp_path):
    result = _run_cli("research", "providers", "--root", str(tmp_path), "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert [provider["provider_id"] for provider in payload["providers"]] == [
        "fake",
        "codex",
        "tavily",
        "searxng",
        "browser",
    ]


def test_supervisor_research_search_records_tavily_preflight_failure(
    tmp_path,
    monkeypatch,
):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    result = _run_cli(
        "research",
        "--root",
        str(tmp_path),
        "--query",
        "agent memory retrieval",
        "--provider",
        "tavily",
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "provider_failed"
    assert payload["error"]["retryable"] is False
    assert payload["error"]["details"]["provider_id"] == "tavily"
    assert payload["artifacts"][0]["artifact_type"] == "research.provider_trace"


def test_supervisor_research_accepts_tavily_config_path(tmp_path, monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    config_path = tmp_path / "research_tavily.toml"
    config_path.write_text('api_key = "test-secret-key"\n', encoding="utf-8")

    result = _run_cli(
        "research",
        "--root",
        str(tmp_path),
        "--query",
        "agent memory retrieval",
        "--provider",
        "tavily",
        "--tavily-config",
        str(config_path),
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "provider_failed"
    assert payload["error"]["details"]["error_code"] == "network_execution_deferred"
    assert "test-secret-key" not in result.stdout


def test_supervisor_research_plain_output_lists_artifacts(tmp_path):
    result = _run_cli(
        "research",
        "--root",
        str(tmp_path),
        "--query",
        "agent memory retrieval",
        "--provider",
        "fake",
    )

    assert result.returncode == 0, result.stderr
    assert "[Codex Supervisor Research]" in result.stdout
    assert "artifact: research.raw_transcript artifact_001" in result.stdout
    assert "artifact: research.report artifact_002" in result.stdout


def test_supervisor_research_list_proxies_research_artifact_list_json(tmp_path):
    store = ArtifactStore(tmp_path)
    artifact = store.create_artifact(
        "run_001",
        execution_id="exec_001",
        artifact_type="research.provider_trace",
        summary="provider failure trace: python docs",
        content='{"status":"provider_failed"}',
    )
    store.create_artifact(
        "run_001",
        execution_id="exec_001",
        artifact_type="text",
        summary="not research",
        content="plain text",
    )

    result = _run_cli(
        "research",
        "list",
        "--root",
        str(tmp_path),
        "--artifact-type",
        "research.provider_trace",
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["count"] == 1
    assert payload["artifacts"][0]["run_id"] == "run_001"
    assert payload["artifacts"][0]["artifact_id"] == artifact.artifact_id


def test_supervisor_research_list_plain_output_is_copyable(tmp_path):
    store = ArtifactStore(tmp_path)
    artifact = store.create_artifact(
        "run_001",
        execution_id="exec_001",
        artifact_type="research.report",
        summary="Fake research summary.",
        content='{"status":"ok"}',
    )

    result = _run_cli("research", "list", "--root", str(tmp_path), "--limit", "1")

    assert result.returncode == 0, result.stderr
    assert "status: ok" in result.stdout
    assert "artifacts: 1" in result.stdout
    assert f"artifact: research.report {artifact.artifact_id} run: run_001 Fake research summary." in result.stdout


def test_supervisor_research_inspect_proxies_research_artifact_json(tmp_path):
    store = ArtifactStore(tmp_path)
    artifact = store.create_artifact(
        "run_001",
        execution_id="exec_001",
        artifact_type="research.report",
        summary="Fake research summary.",
        content='{"status":"ok","report":{"summary":"Fake research summary."}}',
    )

    result = _run_cli(
        "research",
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
    assert payload["artifact"]["artifact_type"] == "research.report"
    assert payload["artifact"]["ref"] == artifact.ref.to_dict()
    assert payload["content"]["report"]["summary"] == "Fake research summary."


def test_supervisor_research_inspect_plain_output_summarizes_provider_trace(tmp_path):
    store = ArtifactStore(tmp_path)
    artifact = store.create_artifact(
        "run_001",
        execution_id="exec_001",
        artifact_type="research.provider_trace",
        summary="provider failure trace: python docs",
        content=json.dumps(
            {
                "status": "provider_failed",
                "provider": "codex_delegated",
                "query": "python docs",
                "error": {
                    "code": "research_provider_failed",
                    "message": "codex cli did not return an agent message",
                    "retryable": True,
                    "details": {
                        "attempt_count": 1,
                        "retry_exhausted": True,
                        "attempts": [
                            {
                                "attempt": 1,
                                "retryable": True,
                                "message": "codex cli did not return an agent message: request timed out",
                                "details": {
                                    "codex_error_messages": ["request timed out on attempt 1"],
                                },
                            }
                        ],
                    },
                },
            }
        ),
    )

    result = _run_cli(
        "research",
        "inspect",
        "--root",
        str(tmp_path),
        "--run-id",
        "run_001",
        "--artifact-id",
        artifact.artifact_id,
    )

    assert result.returncode == 0, result.stderr
    assert f"artifact: research.provider_trace {artifact.artifact_id}" in result.stdout
    assert "attempts: 1 retry_exhausted: true" in result.stdout
    assert "- attempt 1 retryable: true request timed out on attempt 1" in result.stdout
