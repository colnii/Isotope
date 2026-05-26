from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys

from isotope.features.research.runner import _build_parser, _print_plain
from isotope.workspace.artifacts import ArtifactStore


REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = REPO_ROOT / "src"


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "isotope.features.research.runner", *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )


def test_research_cli_search_returns_json(tmp_path):
    result = _run_cli(
        "search",
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
    assert payload["research"]["provider"] == "fake"
    assert payload["research"]["sources"][0]["url"] == "https://example.com/isotope-research"
    assert len(payload["artifact_refs"]) == 2
    assert [artifact["artifact_type"] for artifact in payload["artifacts"]] == [
        "research.raw_transcript",
        "research.report",
    ]


def test_research_cli_lists_provider_registry_json():
    result = _run_cli("providers", "--json")

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
    assert payload["providers"][0]["implemented"] is True
    assert payload["providers"][2]["implemented"] is True


def test_research_cli_providers_plain_output_marks_planned_provider():
    result = _run_cli("providers")

    assert result.returncode == 0, result.stderr
    assert "provider: fake implemented provider_name: fake" in result.stdout
    assert "provider: tavily implemented provider_name: tavily" in result.stdout


def test_research_cli_search_records_tavily_preflight_failure(tmp_path, monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    result = _run_cli(
        "search",
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
    assert payload["error"]["details"]["error_code"] == "missing_api_key"
    assert [artifact["artifact_type"] for artifact in payload["artifacts"]] == [
        "research.provider_trace"
    ]


def test_research_cli_tavily_preflight_does_not_echo_api_key(tmp_path, monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    result = _run_cli(
        "search",
        "--root",
        str(tmp_path),
        "--query",
        "agent memory retrieval",
        "--provider",
        "tavily",
        "--tavily-api-key",
        "test-secret-key",
        "--tavily-timeout-seconds",
        "9",
        "--tavily-max-results",
        "3",
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "provider_failed"
    assert payload["error"]["details"]["error_code"] == "network_execution_deferred"
    assert payload["error"]["details"]["api_key_configured"] is True
    assert payload["error"]["details"]["timeout_seconds"] == 9
    assert payload["error"]["details"]["max_results"] == 3
    assert "test-secret-key" not in result.stdout


def test_research_cli_accepts_tavily_network_gate_args(tmp_path):
    parser = _build_parser()

    args = parser.parse_args(
        [
            "search",
            "--root",
            str(tmp_path),
            "--query",
            "agent memory retrieval",
            "--provider",
            "tavily",
            "--tavily-enable-network",
            "--tavily-api-key",
            "test-secret-key",
            "--tavily-timeout-seconds",
            "9",
            "--tavily-max-results",
            "3",
        ]
    )

    assert args.provider == "tavily"
    assert args.tavily_enable_network is True
    assert args.tavily_api_key == "test-secret-key"
    assert args.tavily_timeout_seconds == 9
    assert args.tavily_max_results == 3


def test_research_cli_plain_output_lists_artifacts(tmp_path):
    result = _run_cli(
        "search",
        "--root",
        str(tmp_path),
        "--query",
        "agent memory retrieval",
        "--provider",
        "fake",
    )

    assert result.returncode == 0, result.stderr
    assert "status: ok" in result.stdout
    assert "artifact: research.raw_transcript artifact_001" in result.stdout
    assert "artifact: research.report artifact_002" in result.stdout


def test_research_cli_inspect_returns_research_artifact_json(tmp_path):
    search = _run_cli(
        "search",
        "--root",
        str(tmp_path),
        "--query",
        "agent memory retrieval",
        "--provider",
        "fake",
        "--json",
    )
    assert search.returncode == 0, search.stderr

    result = _run_cli(
        "inspect",
        "--root",
        str(tmp_path),
        "--run-id",
        "run_001",
        "--artifact-id",
        "artifact_002",
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["artifact"]["artifact_type"] == "research.report"
    assert payload["artifact"]["summary"] == "Fake research summary for agent memory retrieval."
    assert payload["artifact"]["ref"] == {
        "ref_type": "artifact",
        "scope": "run",
        "run_id": "run_001",
        "artifact_id": "artifact_002",
    }
    assert payload["content"]["report"]["summary"] == "Fake research summary for agent memory retrieval."


def test_research_cli_inspect_prints_research_artifact_plain(tmp_path):
    search = _run_cli(
        "search",
        "--root",
        str(tmp_path),
        "--query",
        "agent memory retrieval",
        "--provider",
        "fake",
    )
    assert search.returncode == 0, search.stderr

    result = _run_cli(
        "inspect",
        "--root",
        str(tmp_path),
        "--run-id",
        "run_001",
        "--artifact-id",
        "artifact_001",
    )

    assert result.returncode == 0, result.stderr
    assert "status: ok" in result.stdout
    assert "artifact: research.raw_transcript artifact_001" in result.stdout
    assert "summary: raw research provider output: agent memory retrieval" in result.stdout
    assert '"provider": "fake"' in result.stdout


def test_research_cli_inspect_rejects_non_research_artifact(tmp_path):
    store = ArtifactStore(tmp_path)
    artifact = store.create_artifact(
        "run_001",
        execution_id="exec_001",
        artifact_type="text",
        summary="plain text",
        content="not research",
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
    assert payload["error"]["code"] == "research_runner_error"
    assert payload["error"]["message"] == "artifact is not a research artifact"


def test_research_cli_inspect_reports_missing_artifact_as_runner_error(tmp_path):
    result = _run_cli(
        "inspect",
        "--root",
        str(tmp_path),
        "--run-id",
        "run_001",
        "--artifact-id",
        "artifact_missing",
        "--json",
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "research_runner_error"
    assert "artifact not found" in payload["error"]["message"]


def test_research_plain_output_lists_provider_failure_diagnostics(capsys):
    _print_plain(
        {
            "status": "provider_failed",
            "query": "python docs",
            "artifact_refs": [
                {
                    "ref_type": "artifact",
                    "scope": "run",
                    "run_id": "run_001",
                    "artifact_id": "artifact_001",
                }
            ],
            "artifacts": [
                {
                    "artifact_type": "research.provider_trace",
                    "ref": {
                        "ref_type": "artifact",
                        "scope": "run",
                        "run_id": "run_001",
                        "artifact_id": "artifact_001",
                    },
                    "summary": "provider failure trace: python docs",
                }
            ],
            "error": {
                "code": "research_provider_failed",
                "details": {
                    "attempt_count": 2,
                    "retry_exhausted": True,
                    "attempts": [
                        {
                            "attempt": 1,
                            "retryable": True,
                            "message": "codex cli did not return an agent message: request timed out",
                            "details": {
                                "codex_error_messages": ["request timed out on attempt 1"],
                            },
                        },
                        {
                            "attempt": 2,
                            "retryable": True,
                            "message": "codex cli did not return an agent message: request timed out",
                            "details": {
                                "codex_error_messages": ["request timed out on attempt 2"],
                            },
                        },
                    ],
                },
                "message": "codex cli did not return an agent message",
                "retryable": True,
            },
        }
    )

    output = capsys.readouterr().out

    assert "status: provider_failed" in output
    assert "query: python docs" in output
    assert "retryable: true" in output
    assert "error: codex cli did not return an agent message" in output
    assert "attempts: 2 retry_exhausted: true" in output
    assert "- attempt 1 retryable: true request timed out on attempt 1" in output
    assert "- attempt 2 retryable: true request timed out on attempt 2" in output
    assert "artifact: research.provider_trace artifact_001" in output


def test_research_cli_inspect_prints_provider_trace_attempt_summary(tmp_path):
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
                        "attempt_count": 2,
                        "retry_exhausted": True,
                        "attempts": [
                            {
                                "attempt": 1,
                                "retryable": True,
                                "message": "codex cli did not return an agent message: request timed out",
                                "details": {
                                    "codex_error_messages": ["request timed out on attempt 1"],
                                },
                            },
                            {
                                "attempt": 2,
                                "retryable": True,
                                "message": "codex cli did not return an agent message: request timed out",
                                "details": {
                                    "codex_error_messages": ["request timed out on attempt 2"],
                                },
                            },
                        ],
                    },
                },
            }
        ),
    )

    result = _run_cli(
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
    assert "attempts: 2 retry_exhausted: true" in result.stdout
    assert "- attempt 1 retryable: true request timed out on attempt 1" in result.stdout
    assert "- attempt 2 retryable: true request timed out on attempt 2" in result.stdout


def test_research_cli_list_returns_recent_research_artifacts_json(tmp_path):
    store = ArtifactStore(tmp_path)
    report = store.create_artifact(
        "run_001",
        execution_id="exec_001",
        artifact_type="research.report",
        summary="old report",
        content='{"status":"ok"}',
    )
    store.create_artifact(
        "run_001",
        execution_id="exec_001",
        artifact_type="text",
        summary="not research",
        content="plain text",
    )
    trace = store.create_artifact(
        "run_002",
        execution_id="exec_002",
        artifact_type="research.provider_trace",
        summary="new provider trace",
        content='{"status":"provider_failed"}',
    )
    old_mtime = datetime(2026, 5, 24, tzinfo=timezone.utc).timestamp()
    new_mtime = datetime(2026, 5, 25, tzinfo=timezone.utc).timestamp()
    os.utime(store.artifact_path(report.run_id, report.artifact_id), (old_mtime, old_mtime))
    os.utime(store.artifact_path(trace.run_id, trace.artifact_id), (new_mtime, new_mtime))

    result = _run_cli("list", "--root", str(tmp_path), "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["count"] == 2
    assert [artifact["artifact_type"] for artifact in payload["artifacts"]] == [
        "research.provider_trace",
        "research.report",
    ]
    assert payload["artifacts"][0]["run_id"] == "run_002"
    assert payload["artifacts"][0]["artifact_id"] == trace.artifact_id
    assert payload["artifacts"][0]["ref"] == trace.ref.to_dict()


def test_research_cli_list_prints_copyable_artifact_refs(tmp_path):
    store = ArtifactStore(tmp_path)
    artifact = store.create_artifact(
        "run_001",
        execution_id="exec_001",
        artifact_type="research.provider_trace",
        summary="provider failure trace: python docs",
        content='{"status":"provider_failed"}',
    )

    result = _run_cli("list", "--root", str(tmp_path), "--limit", "1")

    assert result.returncode == 0, result.stderr
    assert "status: ok" in result.stdout
    assert "artifacts: 1" in result.stdout
    assert (
        f"artifact: research.provider_trace {artifact.artifact_id} "
        "run: run_001 provider failure trace: python docs"
    ) in result.stdout


def test_research_cli_list_accepts_type_filter(tmp_path):
    parser = _build_parser()

    args = parser.parse_args(
        [
            "list",
            "--root",
            str(tmp_path),
            "--artifact-type",
            "research.provider_trace",
            "--limit",
            "5",
        ]
    )

    assert args.command == "list"
    assert args.artifact_type == "research.provider_trace"
    assert args.limit == 5


def test_research_cli_requires_query(tmp_path):
    result = _run_cli("search", "--root", str(tmp_path), "--provider", "fake", "--json")

    assert result.returncode == 2
    assert json.loads(result.stdout)["error"]["code"] == "research_runner_error"


def test_research_cli_accepts_codex_provider_args(tmp_path):
    parser = _build_parser()

    args = parser.parse_args(
        [
            "search",
            "--root",
            str(tmp_path),
            "--query",
            "agent memory retrieval",
            "--provider",
            "codex",
            "--workspace-root",
            str(tmp_path),
            "--codex-executable",
            "codex",
            "--timeout-seconds",
            "60",
            "--max-attempts",
            "2",
        ]
    )

    assert args.provider == "codex"
    assert args.workspace_root == str(tmp_path)
    assert args.codex_executable == "codex"
    assert args.timeout_seconds == 60
    assert args.max_attempts == 2
