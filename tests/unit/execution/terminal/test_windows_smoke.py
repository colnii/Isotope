from __future__ import annotations

import json
from pathlib import Path

from isotope.execution.terminal.windows_smoke import (
    WindowsSmokePlan,
    WindowsSmokeReport,
    WindowsSmokeStep,
    WindowsSmokeStepResult,
    redact_public_summary,
)


def test_windows_smoke_plan_serializes_structured_steps_without_shell_strings(tmp_path):
    step = WindowsSmokeStep(
        name="python_version",
        argv=["python", "--version"],
        cwd=".",
        env_overlay={"PYTHONUTF8": "1"},
        required_artifacts=[],
    )
    plan = WindowsSmokePlan(
        source_root=tmp_path,
        profile_id="desktop_tools_versions",
        profile_version="2026-06-02",
        workspace_strategy="auto",
        steps=[step],
        timeout_seconds=30,
        max_output_bytes=2048,
    )

    payload = plan.to_dict()

    assert payload["source_root"] == str(tmp_path)
    assert payload["workspace_strategy"] == "auto"
    assert payload["steps"][0]["argv"] == ["python", "--version"]
    assert payload["steps"][0]["env_overlay"] == {"PYTHONUTF8": "1"}
    assert "command" not in payload["steps"][0]


def test_windows_smoke_report_keeps_diagnostics_separate_from_public_summary(tmp_path):
    user_home = tmp_path / "Users" / "lumber"
    copied_workspace = tmp_path / "isotope-smoke" / "run-001"
    full_stdout = f"node ok from {copied_workspace}"
    step = WindowsSmokeStepResult(
        name="node_version",
        argv=["node", "--version"],
        cwd=str(copied_workspace / "apps" / "desktop"),
        started_at="2026-06-02T00:00:00Z",
        finished_at="2026-06-02T00:00:01Z",
        exit_code=0,
        stdout=full_stdout,
        stderr=f"warning under {user_home}",
        truncated=False,
        reason_code="windows_smoke_command_completed",
        artifacts=[str(copied_workspace / "node-version.txt")],
        copied_workspace_path=str(copied_workspace),
        process_tree_cleanup={"attempted": False, "succeeded": None, "method": None},
    )
    diagnostic_report = {
        "source_root": str(user_home / "Github" / "isotope"),
        "workspace_root": str(copied_workspace),
        "steps": [step.to_dict()],
    }
    public_summary = redact_public_summary(
        status="completed",
        reason_code="windows_smoke_completed",
        profile_id="desktop_tools_versions",
        host_mode="windows_python",
        workspace_strategy_decision={"strategy": "copy_to_temp", "workspace_root": str(copied_workspace)},
        diagnostic_report=diagnostic_report,
        redaction_paths=[str(user_home), str(copied_workspace)],
    )
    report = _golden_report(
        diagnostic_report=diagnostic_report,
        public_summary=public_summary,
    )

    payload = report.to_dict()
    public_json = json.dumps(payload["public_summary"], sort_keys=True)

    assert full_stdout in json.dumps(payload["diagnostic_report"], sort_keys=True)
    assert str(copied_workspace) in json.dumps(payload["diagnostic_report"], sort_keys=True)
    assert full_stdout not in public_json
    assert str(copied_workspace) not in public_json
    assert str(user_home) not in public_json
    assert payload["public_summary"]["step_summaries"] == [
        {
            "name": "node_version",
            "exit_code": 0,
            "reason_code": "windows_smoke_command_completed",
            "truncated": False,
        }
    ]


def test_windows_smoke_report_matches_golden_fixture():
    fixture = Path("tests/fixtures/windows_smoke_report.golden.json")
    assert json.loads(_golden_report().to_json()) == json.loads(fixture.read_text())


def _golden_report(
    *,
    diagnostic_report: dict | None = None,
    public_summary: dict | None = None,
) -> WindowsSmokeReport:
    if diagnostic_report is None:
        step = WindowsSmokeStepResult(
            name="node_version",
            argv=["node", "--version"],
            cwd="C:\\isotope-smoke\\run-001\\apps\\desktop",
            started_at="2026-06-02T00:00:00Z",
            finished_at="2026-06-02T00:00:01Z",
            exit_code=0,
            stdout="v22.11.0\n",
            stderr="",
            truncated=False,
            reason_code="windows_smoke_command_completed",
            artifacts=["C:\\isotope-smoke\\run-001\\node-version.txt"],
            copied_workspace_path="C:\\isotope-smoke\\run-001",
            process_tree_cleanup={"attempted": False, "succeeded": None, "method": None},
        )
        diagnostic_report = {
            "source_root": "C:\\Users\\lumber\\Github\\isotope",
            "workspace_root": "C:\\isotope-smoke\\run-001",
            "steps": [step.to_dict()],
        }
    if public_summary is None:
        public_summary = {
            "status": "completed",
            "reason_code": "windows_smoke_completed",
            "profile_id": "desktop_tools_versions",
            "host_mode": "windows_python",
            "workspace_strategy": "copy_to_temp",
            "step_summaries": [
                {
                    "name": "node_version",
                    "exit_code": 0,
                    "reason_code": "windows_smoke_command_completed",
                    "truncated": False,
                }
            ],
        }
    return WindowsSmokeReport(
        runner_version="windows-smoke-runner.v0.1",
        profile_id="desktop_tools_versions",
        profile_version="2026-06-02",
        host_mode="windows_python",
        platform_info={"machine": "AMD64", "release": "11", "system": "Windows"},
        tool_versions={"node": "v22.11.0", "npm": "10.9.0", "python": "3.13.3"},
        source_root_kind="windows_local",
        workspace_strategy_decision={
            "strategy": "copy_to_temp",
            "reason": "mutation_policy_requires_copy",
        },
        repo_revision_if_available="abc1234",
        started_at="2026-06-02T00:00:00Z",
        finished_at="2026-06-02T00:00:01Z",
        status="completed",
        reason_code="windows_smoke_completed",
        diagnostic_report=diagnostic_report,
        public_summary=public_summary,
    )
