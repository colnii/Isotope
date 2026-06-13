from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
import subprocess
import sys
from typing import Any

from isotope.platform.schemas.memory import MemoryRecord
from isotope.workspace.artifacts import ArtifactStore


REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = REPO_ROOT / "src"

FORBIDDEN_KEYS = {
    "api_key",
    "content",
    "full_content",
    "local_path",
    "prompt",
    "raw_content",
    "trace",
    "transcript",
}


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "isotope.capabilities.runner", *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )


def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _assert_public_metadata(value: Any) -> None:
    for mapping in _walk(value):
        assert FORBIDDEN_KEYS.isdisjoint(mapping)


def test_capability_runner_cli_lists_capabilities_as_json():
    result = _run_cli("list", "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    capability_ids = [item["capability_id"] for item in payload["capabilities"]]
    assert set(capability_ids).issuperset({
        "approval.tool.runner",
        "artifact.changed_files",
        "artifact.diff_result",
        "artifact.review",
        "code.read",
        "code.search",
        "coding_task.execute",
        "external.snapshot.review",
        "mcp.servers.list",
        "mcp.tool.call",
        "mcp.tools.search",
        "memory.promotion.preview",
        "memory.query",
        "research.promote",
        "research.search",
        "screen.report",
        "skills.describe",
        "skills.search",
        "supervisor.codex_operation",
        "supervisor.goal_plan",
        "supervisor.integration_review",
        "supervisor.request_context",
        "supervisor.worker_review",
    })
    _assert_public_metadata(payload)


def test_capability_runner_cli_describes_capability_as_json():
    result = _run_cli("describe", "artifact.review", "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["capability"]["capability_id"] == "artifact.review"
    assert payload["capability"]["shelf"] == "product_candidate"
    _assert_public_metadata(payload)


def test_capability_runner_cli_reports_status_as_json():
    result = _run_cli("status", "external.snapshot.review", "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["capability_status"]["capability_id"] == "external.snapshot.review"
    assert payload["capability_status"]["ready"] is True
    assert payload["capability_status"]["status"] == "ready"
    _assert_public_metadata(payload)


def test_capability_runner_cli_searches_capabilities_as_json():
    result = _run_cli("search", "artifact", "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["search"]["kind"] == "capability_search_result"
    assert payload["search"]["query"] == "artifact"
    capability_ids = [item["capability_id"] for item in payload["search"]["capabilities"]]
    assert "artifact.review" in capability_ids
    assert "artifact.changed_files" in capability_ids
    _assert_public_metadata(payload)


def test_capability_runner_cli_searches_supervisor_request_context_as_json():
    result = _run_cli("search", "request_context", "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert [item["capability_id"] for item in payload["search"]["capabilities"]] == [
        "supervisor.request_context"
    ]
    _assert_public_metadata(payload)


def test_capability_runner_cli_searches_supervisor_integration_review_as_json():
    result = _run_cli("search", "integration-review", "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert [item["capability_id"] for item in payload["search"]["capabilities"]] == [
        "supervisor.integration_review"
    ]
    _assert_public_metadata(payload)


def test_capability_runner_cli_searches_supervisor_worker_review_as_json():
    result = _run_cli("search", "worker-review", "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert [item["capability_id"] for item in payload["search"]["capabilities"]] == [
        "supervisor.worker_review"
    ]
    _assert_public_metadata(payload)


def test_capability_runner_cli_searches_supervisor_goal_plan_as_json():
    result = _run_cli("search", "goal plan", "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert "supervisor.goal_plan" in [
        item["capability_id"] for item in payload["search"]["capabilities"]
    ]
    _assert_public_metadata(payload)


def test_capability_runner_cli_searches_screen_report_as_json():
    result = _run_cli("search", "screen report", "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert "screen.report" in [
        item["capability_id"] for item in payload["search"]["capabilities"]
    ]
    _assert_public_metadata(payload)


def test_capability_runner_cli_searches_research_search_as_json():
    result = _run_cli("search", "research search", "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert [item["capability_id"] for item in payload["search"]["capabilities"]] == [
        "research.search"
    ]
    _assert_public_metadata(payload)


def test_capability_runner_cli_searches_research_promote_as_json():
    result = _run_cli("search", "research promote", "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert [item["capability_id"] for item in payload["search"]["capabilities"]] == [
        "research.promote"
    ]
    _assert_public_metadata(payload)


def test_capability_runner_cli_plans_capability_run_as_json():
    result = _run_cli("plan", "artifact.review", "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    plan = payload["plan"]
    assert plan["kind"] == "capability_launch_plan"
    assert plan["capability_id"] == "artifact.review"
    assert plan["can_launch"] is True
    assert plan["runner_kind"] == "deterministic_demo"
    assert plan["scenario"] == "artifact-review"
    _assert_public_metadata(payload)


def test_capability_runner_cli_plans_request_context_missing_inputs_as_json():
    result = _run_cli(
        "plan",
        "supervisor.request_context",
        "--input-json",
        json.dumps({"cwd": "/tmp/project"}),
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    plan = payload["plan"]
    assert plan["capability_id"] == "supervisor.request_context"
    assert plan["can_launch"] is False
    assert plan["status"] == "missing_inputs"
    assert plan["runner_kind"] == "deterministic_projection"
    assert plan["missing_inputs"] == ["state_root", "query"]
    _assert_public_metadata(payload)


def test_capability_runner_cli_plans_worker_review_missing_inputs_as_json():
    result = _run_cli("plan", "supervisor.worker_review", "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    plan = payload["plan"]
    assert plan["capability_id"] == "supervisor.worker_review"
    assert plan["can_launch"] is False
    assert plan["status"] == "missing_inputs"
    assert plan["runner_kind"] == "deterministic_projection"
    assert plan["missing_inputs"] == ["state_root"]
    _assert_public_metadata(payload)


def test_capability_runner_cli_plans_integration_review_missing_inputs_as_json():
    result = _run_cli("plan", "supervisor.integration_review", "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    plan = payload["plan"]
    assert plan["capability_id"] == "supervisor.integration_review"
    assert plan["can_launch"] is False
    assert plan["status"] == "missing_inputs"
    assert plan["runner_kind"] == "deterministic_projection"
    assert plan["missing_inputs"] == ["state_root"]
    _assert_public_metadata(payload)


def test_capability_runner_cli_plans_goal_plan_missing_inputs_as_json():
    result = _run_cli("plan", "supervisor.goal_plan", "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    plan = payload["plan"]
    assert plan["capability_id"] == "supervisor.goal_plan"
    assert plan["can_launch"] is False
    assert plan["status"] == "missing_inputs"
    assert plan["runner_kind"] == "supervisor_goal_plan"
    assert plan["missing_inputs"] == ["state_root", "cwd", "goal"]
    _assert_public_metadata(payload)


def test_capability_runner_cli_plans_memory_query_missing_inputs_as_json():
    result = _run_cli(
        "plan",
        "memory.query",
        "--input-json",
        json.dumps({"root": "/tmp/isotope-runtime", "query": "memory"}),
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    plan = payload["plan"]
    assert plan["capability_id"] == "memory.query"
    assert plan["can_launch"] is False
    assert plan["status"] == "missing_inputs"
    assert plan["runner_kind"] == "deterministic_projection"
    assert plan["missing_inputs"] == ["run_id"]
    _assert_public_metadata(payload)


def test_capability_runner_cli_plans_screen_report_missing_inputs_as_json():
    result = _run_cli(
        "plan",
        "screen.report",
        "--input-json",
        json.dumps({"root": "/tmp/isotope-runtime"}),
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    plan = payload["plan"]
    assert plan["capability_id"] == "screen.report"
    assert plan["can_launch"] is False
    assert plan["status"] == "missing_inputs"
    assert plan["runner_kind"] == "deterministic_projection"
    assert plan["missing_inputs"] == ["run_id"]
    _assert_public_metadata(payload)


def test_capability_runner_cli_plans_research_search_missing_inputs_as_json():
    result = _run_cli(
        "plan",
        "research.search",
        "--input-json",
        json.dumps({"root": "/tmp/isotope-runtime"}),
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    plan = payload["plan"]
    assert plan["capability_id"] == "research.search"
    assert plan["can_launch"] is False
    assert plan["status"] == "missing_inputs"
    assert plan["runner_kind"] == "deterministic_local"
    assert plan["missing_inputs"] == ["query"]
    _assert_public_metadata(payload)


def test_capability_runner_cli_plans_research_promote_missing_inputs_as_json():
    result = _run_cli(
        "plan",
        "research.promote",
        "--input-json",
        json.dumps(
            {
                "root": "/tmp/isotope-runtime",
                "run_id": "run_research",
                "artifact_id": "artifact_report",
            }
        ),
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    plan = payload["plan"]
    assert plan["capability_id"] == "research.promote"
    assert plan["can_launch"] is False
    assert plan["status"] == "missing_inputs"
    assert plan["runner_kind"] == "deterministic_local"
    assert plan["missing_inputs"] == ["agent_id", "thread_id"]
    _assert_public_metadata(payload)


def test_capability_runner_cli_rejects_non_object_input_json():
    result = _run_cli(
        "plan",
        "supervisor.request_context",
        "--input-json",
        json.dumps(["not", "an", "object"]),
        "--json",
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload == {
        "status": "error",
        "error": {
            "code": "capability_runner_error",
            "message": "input JSON must be an object",
        },
    }


def test_capability_runner_cli_rejects_required_input_type_errors(tmp_path):
    result = _run_cli(
        "run",
        "supervisor.request_context",
        "--input-json",
        json.dumps(
            {
                "state_root": str(tmp_path / "supervisor-state"),
                "cwd": str(tmp_path),
                "query": 123,
            }
        ),
        "--json",
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "capability_runner_error"
    assert payload["error"]["message"] == "query must be a string"


def test_capability_runner_cli_rejects_invalid_max_results(tmp_path):
    result = _run_cli(
        "run",
        "supervisor.request_context",
        "--input-json",
        json.dumps(
            {
                "state_root": str(tmp_path / "supervisor-state"),
                "cwd": str(tmp_path),
                "query": "request_context",
                "max_results": 0,
            }
        ),
        "--json",
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "capability_runner_error"
    assert payload["error"]["message"] == "max_results must be a positive integer"


def test_capability_runner_cli_runs_allowlisted_capability_as_json(tmp_path):
    result = _run_cli("run", "artifact.review", "--root", str(tmp_path), "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    run = payload["run"]
    assert run["capability_id"] == "artifact.review"
    assert run["status"] == "completed"
    assert run["scenario"] == "artifact-review"
    assert run["replay_ok"] is True
    assert run["checkpoint_ok"] is True
    _assert_public_metadata(payload)


def test_capability_runner_cli_runs_request_context_with_input_json(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "notes.md").write_text(
        "Supervisor request_context can retrieve project context.\n",
        encoding="utf-8",
    )
    state_root = tmp_path / "supervisor-state"
    input_json = json.dumps(
        {
            "state_root": str(state_root),
            "cwd": str(workspace),
            "query": "request_context project context",
            "max_results": 2,
        }
    )

    result = _run_cli(
        "run",
        "supervisor.request_context",
        "--input-json",
        input_json,
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    run = payload["run"]
    assert run["capability_id"] == "supervisor.request_context"
    assert run["status"] == "completed"
    assert run["runner_kind"] == "deterministic_projection"
    assert run["context_result"]["backend"] == "bm25"
    assert isinstance(run["context_result"]["created_at"], str)
    assert run["context_result"]["created_at"]
    assert run["context_result"]["item_count"] >= 1
    assert (state_root / "supervisor" / "context_results.jsonl").is_file()
    _assert_public_metadata(payload)


def test_capability_runner_cli_runs_worker_review_with_input_json(tmp_path):
    state_root = tmp_path / "supervisor-state"
    input_json = json.dumps({"state_root": str(state_root)})

    result = _run_cli(
        "run",
        "supervisor.worker_review",
        "--input-json",
        input_json,
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    run = payload["run"]
    assert run["capability_id"] == "supervisor.worker_review"
    assert run["status"] == "completed"
    assert run["runner_kind"] == "deterministic_projection"
    assert run["worker_review"]["status"] == "ok"
    assert run["worker_review"]["summary"]["total"] == 0
    assert run["worker_review"]["workers"] == []
    _assert_public_metadata(payload)


def test_capability_runner_cli_runs_integration_review_with_input_json(tmp_path):
    state_root = tmp_path / "supervisor-state"
    input_json = json.dumps({"state_root": str(state_root)})

    result = _run_cli(
        "run",
        "supervisor.integration_review",
        "--input-json",
        input_json,
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    run = payload["run"]
    assert run["capability_id"] == "supervisor.integration_review"
    assert run["status"] == "completed"
    assert run["runner_kind"] == "deterministic_projection"
    review = run["integration_review"]
    assert review["status"] == "ok"
    assert review["summary"]["total"] == 0
    assert review["groups"]["ready_to_integrate"] == []
    assert review["workers"] == []
    _assert_public_metadata(payload)


def test_capability_runner_cli_runs_memory_query_with_input_json(tmp_path):
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    _write_memory_record(
        memory_dir,
        MemoryRecord(
            memory_id="mem_cli",
            scope="run",
            content={"raw": "raw memory content must not leak"},
            summary="CLI can recall memory query capability.",
            source_refs=[{"ref_type": "artifact", "artifact_id": "artifact_cli"}],
            provenance={
                "run_id": "run_cli",
                "execution_id": "exec_cli",
                "action_type": "write_memory",
            },
            created_at="2026-05-27T00:00:00Z",
            supersedes=[],
            quality="verified",
        ),
    )

    result = _run_cli(
        "run",
        "memory.query",
        "--input-json",
        json.dumps(
            {
                "root": str(tmp_path),
                "query": "memory query",
                "run_id": "run_cli",
            }
        ),
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    run = payload["run"]
    assert run["capability_id"] == "memory.query"
    assert run["status"] == "completed"
    assert run["runner_kind"] == "deterministic_projection"
    assert run["memory_query"]["content_policy"] == "memory_record_refs_expandable"
    assert run["memory_query"]["results"][0]["record_id"] == "mem_cli"
    assert "raw memory content" not in result.stdout
    _assert_public_metadata(payload)


def test_capability_runner_cli_runs_memory_promotion_preview_with_input_json():
    result = _run_cli(
        "run",
        "memory.promotion.preview",
        "--input-json",
        json.dumps(
            {
                "run_id": "run_memory",
                "agent_id": "agent_memo",
                "thread_id": "thread_memory",
                "candidate": {
                    "source_type": "artifact",
                    "artifact_ref": {
                        "ref_type": "artifact",
                        "scope": "run",
                        "run_id": "run_memory",
                        "artifact_id": "artifact_report",
                    },
                    "artifact_type": "research.report",
                    "summary": "Promote report summary into memory.",
                    "provenance": {"execution_id": "exec_report"},
                },
            }
        ),
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    run = payload["run"]
    assert run["capability_id"] == "memory.promotion.preview"
    assert run["status"] == "completed"
    assert run["runner_kind"] == "deterministic_projection"
    preview = run["memory_promotion_preview"]
    assert preview["action_type"] == "write_memory"
    assert preview["content_policy"] == "memory_record_refs_expandable"
    assert preview["source_refs"][0]["artifact_id"] == "artifact_report"
    assert "raw_content" not in result.stdout
    assert "raw memory content" not in result.stdout
    _assert_public_metadata(payload)


def test_capability_runner_cli_runs_screen_report_with_input_json(tmp_path):
    store = ArtifactStore(tmp_path)
    store.create_artifact(
        "run_screen",
        execution_id="exec_screen",
        artifact_type="screen_control_plan",
        summary="screen control result",
        content=json.dumps(
            {
                "action_count": 1,
                "executed": False,
                "planned_actions": ["restore_window"],
                "private_note": "raw screen control payload must not leak",
            },
            sort_keys=True,
        ),
    )

    result = _run_cli(
        "run",
        "screen.report",
        "--input-json",
        json.dumps(
            {
                "root": str(tmp_path),
                "run_id": "run_screen",
            }
        ),
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    run = payload["run"]
    assert run["capability_id"] == "screen.report"
    assert run["status"] == "completed"
    assert run["runner_kind"] == "deterministic_projection"
    assert run["screen_report"]["summary"]["control_status"] == "planned"
    assert run["screen_report"]["summary"]["control_actions"][0]["action_types"] == [
        "restore_window"
    ]
    assert "raw screen control payload" not in result.stdout
    _assert_public_metadata(payload)


def test_capability_runner_cli_describes_screen_control_as_product_candidate():
    result = _run_cli("describe", "screen.control", "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    capability = payload["capability"]
    assert capability["capability_id"] == "screen.control"
    assert capability["shelf"] == "product_candidate"
    assert capability["input_contract"]["required"] == [
        "target_selector",
        "execution_mode",
        "actions",
    ]
    assert "approval_required_for_execute" in capability["safety_boundaries"]
    _assert_public_metadata(payload)


def test_capability_runner_cli_plans_screen_control_missing_actions(tmp_path):
    result = _run_cli(
        "plan",
        "screen.control",
        "--input-json",
        json.dumps(
            {
                "root": str(tmp_path),
                "target_selector": {
                    "kind": "window",
                    "selector": {"app": "notepad.exe"},
                },
                "execution_mode": "dry_run",
            }
        ),
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    plan = payload["plan"]
    assert plan["capability_id"] == "screen.control"
    assert plan["status"] == "missing_inputs"
    assert plan["missing_inputs"] == ["actions"]
    assert plan["runner_kind"] == "deterministic_local"
    _assert_public_metadata(payload)


def test_capability_runner_cli_unknown_capability_fails_controlled_json(tmp_path):
    result = _run_cli("run", "unknown.capability", "--root", str(tmp_path), "--json")

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload == {
        "status": "error",
        "error": {
            "code": "capability_runner_error",
            "message": "unknown capability: unknown.capability",
        },
    }
    assert not list(tmp_path.rglob("*"))


def _write_memory_record(memory_dir: Path, record: MemoryRecord) -> None:
    (memory_dir / f"{record.memory_id}.json").write_text(
        json.dumps(asdict(record), sort_keys=True),
        encoding="utf-8",
    )
