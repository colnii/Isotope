from __future__ import annotations

import json
from pathlib import Path

import pytest

from isotope.execution.terminal.windows_smoke import (
    WindowsSmokeWorkspaceError,
    WindowsSmokePlan,
    WindowsSmokeReport,
    WindowsSmokeStep,
    WindowsSmokeStepResult,
    collect_windows_workspace_copy_items,
    redact_public_summary,
    resolve_windows_host_mode,
    resolve_windows_workspace,
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


def test_resolve_windows_host_mode_is_explicit_and_fail_closed():
    assert resolve_windows_host_mode(platform_name="win32", has_wsl_interop=False) == "windows_python"
    assert resolve_windows_host_mode(platform_name="linux", has_wsl_interop=True) == "wsl_to_windows_helper"
    assert resolve_windows_host_mode(platform_name="linux", has_wsl_interop=False) == "unsupported"
    assert resolve_windows_host_mode(platform_name="darwin", has_wsl_interop=True) == "unsupported"


def test_workspace_resolver_allows_direct_only_for_safe_read_only_windows_paths():
    decision = resolve_windows_workspace(
        source_root="C:\\repo\\isotope",
        host_mode="windows_python",
        workspace_strategy="auto",
        source_root_kind="windows_local",
        mutation_policy="read_only",
        temp_root="C:\\isotope-smoke",
        run_id="run001",
    )

    assert decision.strategy == "direct"
    assert decision.source_root_kind == "windows_local"
    assert decision.workspace_root == "C:\\repo\\isotope"
    assert decision.cleanup_on_success is False
    assert decision.keep_on_failure is True


def test_workspace_resolver_uses_short_temp_copy_for_wsl_mutation_or_long_paths():
    wsl_decision = resolve_windows_workspace(
        source_root="\\\\wsl.localhost\\Ubuntu\\home\\lumber\\Github\\isotope",
        host_mode="wsl_to_windows_helper",
        workspace_strategy="auto",
        source_root_kind="wsl_unc",
        mutation_policy="read_only",
        temp_root="C:\\isotope-smoke",
        run_id="run002",
    )
    mutating_decision = resolve_windows_workspace(
        source_root="C:\\" + ("very-long\\" * 35) + "isotope",
        host_mode="windows_python",
        workspace_strategy="auto",
        source_root_kind="windows_local",
        mutation_policy="build",
        temp_root="C:\\isotope-smoke",
        run_id="run003",
    )
    path_risk_decision = resolve_windows_workspace(
        source_root="C:\\" + ("deep\\" * 60) + "isotope",
        host_mode="windows_python",
        workspace_strategy="auto",
        source_root_kind="windows_local",
        mutation_policy="read_only",
        temp_root="C:\\isotope-smoke",
        run_id="run004",
    )

    assert wsl_decision.strategy == "copy_to_temp"
    assert wsl_decision.workspace_root == "C:\\isotope-smoke\\run002"
    assert wsl_decision.reason == "source_root_requires_windows_local_copy"
    assert mutating_decision.strategy == "copy_to_temp"
    assert mutating_decision.workspace_root == "C:\\isotope-smoke\\run003"
    assert mutating_decision.reason == "mutation_policy_requires_copy"
    assert mutating_decision.cleanup_on_success is True
    assert mutating_decision.keep_on_failure is True
    assert path_risk_decision.strategy == "copy_to_temp"
    assert path_risk_decision.workspace_root == "C:\\isotope-smoke\\run004"
    assert path_risk_decision.reason == "windows_path_length_risk"


def test_workspace_copy_policy_includes_project_files_and_excludes_generated_dirs(tmp_path):
    _touch(tmp_path / "package.json")
    _touch(tmp_path / "package-lock.json")
    _touch(tmp_path / "pyproject.toml")
    _touch(tmp_path / "src" / "isotope" / "__init__.py")
    _touch(tmp_path / "apps" / "desktop" / "src" / "main.ts")
    _touch(tmp_path / "apps" / "desktop" / "node_modules" / "bad.js")
    _touch(tmp_path / ".git" / "config")
    _touch(tmp_path / ".venv" / "pyvenv.cfg")
    _touch(tmp_path / "target" / "debug" / "bad")
    _touch(tmp_path / "build" / "bad")
    _touch(tmp_path / ".svelte-kit" / "bad")

    copy_items = {item.as_posix() for item in collect_windows_workspace_copy_items(tmp_path)}

    assert "package.json" in copy_items
    assert "package-lock.json" in copy_items
    assert "pyproject.toml" in copy_items
    assert "src/isotope/__init__.py" in copy_items
    assert "apps/desktop/src/main.ts" in copy_items
    assert "apps/desktop/node_modules/bad.js" not in copy_items
    assert ".git/config" not in copy_items
    assert ".venv/pyvenv.cfg" not in copy_items
    assert "target/debug/bad" not in copy_items
    assert "build/bad" not in copy_items
    assert ".svelte-kit/bad" not in copy_items


def test_workspace_copy_policy_rejects_symlinks_escaping_source_root(tmp_path):
    outside = tmp_path.parent / "outside-secret"
    outside.mkdir()
    link = tmp_path / "src" / "escape"
    link.parent.mkdir(parents=True)
    link.symlink_to(outside, target_is_directory=True)

    with pytest.raises(WindowsSmokeWorkspaceError) as exc_info:
        collect_windows_workspace_copy_items(tmp_path)

    assert exc_info.value.reason_code == "windows_smoke_workspace_symlink_escape"


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


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x")
