from __future__ import annotations

import json

from isotope.capabilities.runner import CapabilityRunner


def test_supervisor_codex_operation_is_listed_as_unified_capacity():
    runner = CapabilityRunner()

    ids = [item["capability_id"] for item in runner.list_capabilities()]
    description = runner.describe_capability("supervisor.codex_operation")

    assert "supervisor.codex_operation" in ids
    assert description["input_contract"]["required"] == ["operation", "state_root"]
    assert "codex_home" not in description["input_contract"]["properties"]
    assert description["input_contract"]["properties"]["operation"]["enum"] == [
        "request_context",
        "worker_review",
        "integration_review",
        "launch_worker",
        "resume_worker",
        "adopt_resume_by_description",
    ]
    assert "single_supervisor_operation_capacity" in description["safety_boundaries"]


def test_supervisor_codex_operation_plan_requires_operation(tmp_path):
    plan = CapabilityRunner().plan_capability_run(
        "supervisor.codex_operation",
        inputs={"state_root": str(tmp_path)},
    )

    assert plan["can_launch"] is False
    assert plan["status"] == "missing_inputs"
    assert plan["missing_inputs"] == ["operation"]


def test_supervisor_codex_operation_runs_worker_review_through_unified_entry(tmp_path):
    result = CapabilityRunner().run_capability(
        "supervisor.codex_operation",
        inputs={"operation": "worker_review", "state_root": str(tmp_path)},
    )

    assert result["kind"] == "capability_run_result"
    assert result["capability_id"] == "supervisor.codex_operation"
    assert result["status"] == "completed"
    assert result["operation"] == "worker_review"
    assert result["operation_result"]["capability_id"] == "supervisor.worker_review"
    assert "worker_review" in result["operation_result"]
    assert "prompt" not in json.dumps(result, ensure_ascii=False).lower()


def test_supervisor_codex_operation_accepts_legacy_codex_home_alias(tmp_path):
    result = CapabilityRunner().run_capability(
        "supervisor.codex_operation",
        inputs={"operation": "worker_review", "codex_home": str(tmp_path)},
    )

    assert result["status"] == "completed"
    assert result["operation_result"]["capability_id"] == "supervisor.worker_review"
