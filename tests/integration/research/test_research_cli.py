from __future__ import annotations

import json
import os
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
    assert "artifact: research.provider_trace artifact_001" in output


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
