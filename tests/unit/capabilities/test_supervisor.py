import importlib
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

from isotope.capabilities.catalog import Capability, CapabilityCatalog
from isotope.features.supervisor.registry import (
    ManagedCodexRecord,
    append_managed_record,
    default_registry_path,
)
from isotope.platform.schemas.memory import MemoryRecord
from isotope.workspace.artifacts import ArtifactStore


FORBIDDEN_RESULT_KEYS = {
    "api_key",
    "content",
    "full_content",
    "local_path",
    "prompt",
    "raw_content",
    "transcript",
}


def _runner_module():
    return importlib.import_module("isotope.capabilities.runner")


def _runner(*, catalog=None):
    return _runner_module().CapabilityRunner(
        catalog=catalog or CapabilityCatalog.default()
    )


def _ids(entries):
    return [entry["capability_id"] for entry in entries]


def _walk_mapping(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_mapping(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_mapping(child)


def _write_memory_record(memory_dir, record):
    from dataclasses import asdict
    (memory_dir / f"{record.memory_id}.json").write_text(
        json.dumps(asdict(record), sort_keys=True),
        encoding="utf-8",
    )


def _capability(capability_id, shelf, **overrides):
    data = {
        "capability_id": capability_id,
        "title": capability_id.replace(".", " ").title(),
        "description": f"{capability_id} capability metadata.",
        "maturity": "v0.2",
        "shelf": shelf,
        "domain_tags": tuple(capability_id.split(".")),
        "input_contract": {"type": "object"},
        "output_contract": {"type": "object"},
        "safety_boundaries": ("public_metadata_manifest_only",),
        "default_enabled": True,
        "required_env": (),
        "network_required": False,
        "provider": None,
        "model": None,
    }
    data.update(overrides)
    return Capability(**data)

def test_runner_discovers_supervisor_request_context_from_default_catalog():
    runner = _runner()

    assert "supervisor.request_context" in _ids(runner.list_capabilities())
    search = runner.search_capabilities(query="request_context")

    assert _ids(search["capabilities"]) == ["supervisor.request_context"]
    description = runner.describe_capability("supervisor.request_context")
    assert description["input_contract"]["required"] == ["state_root", "cwd", "query"]
    assert "codex_home" not in description["input_contract"]["properties"]
    assert "workspace_context_projection" in description["safety_boundaries"]
    assert "writes_existing_supervisor_context_store" in description["safety_boundaries"]



def test_supervisor_request_context_manifest_uses_context_projection_language():
    description = _runner().describe_capability("supervisor.request_context")
    manifest_text = json.dumps(description, ensure_ascii=False)

    forbidden_terms = [
        "read" + "_snapshot",
        "inspection " + "mode",
        "只读" + "扫描",
        "不" + "执行",
    ]

    assert "context" in description["description"].lower()
    assert "workspace_context_projection" in description["safety_boundaries"]
    for term in forbidden_terms:
        assert term not in manifest_text



def test_runner_discovers_supervisor_project_status_from_default_catalog():
    runner = _runner()

    ids = _ids(runner.list_capabilities())
    assert "supervisor.project_status" in ids
    description = runner.describe_capability("supervisor.project_status")

    assert description["input_contract"]["required"] == ["state_root"]
    assert description["input_contract"]["properties"]["state_root"]["type"] == "string"
    assert "project_state" in description["output_contract"]["fields"]
    assert "public_state_projection" in description["safety_boundaries"]



def test_project_status_capability_returns_public_state_projection(tmp_path):
    runner = _runner()

    result = runner.run_capability(
        "supervisor.project_status",
        inputs={"state_root": str(tmp_path)},
    )

    assert result["kind"] == "capability_run_result"
    assert result["capability_id"] == "supervisor.project_status"
    assert result["status"] == "completed"
    summary = result["project_state"]
    assert summary["snapshot_id"]
    assert summary["counts"]["runningAgents"] == 0
    assert "raw" not in json.dumps(result, ensure_ascii=False).lower()
    assert "messages" not in json.dumps(result, ensure_ascii=False).lower()



def test_project_status_capability_includes_self_repair_worker_status(tmp_path):
    workspace = tmp_path / "repo" / ".worktrees" / "supervisor" / "desktop-self-repair"
    workspace.mkdir(parents=True)
    log_path = tmp_path / "supervisor" / "logs" / "managed-self-repair.log"
    log_path.parent.mkdir(parents=True)
    log_path.write_text(
        "\n".join(
            [
                "SUPERVISOR_STATUS: done",
                "SUPERVISOR_SUMMARY: 已修复 Desktop chat 项目态势读取。",
                "SUPERVISOR_NEXT: 等待主线合并。",
            ]
        ),
        encoding="utf-8",
    )
    append_managed_record(
        default_registry_path(tmp_path),
        ManagedCodexRecord(
            record_id="managed-self-repair",
            name="desktop-self-repair",
            cwd=str(workspace),
            prompt="Isotope self-repair request must stay private.",
            command=("codex", "exec", "-C", str(workspace), "prompt"),
            pid=0,
            started_at="2026-06-04T00:00:00+00:00",
            log_path=str(log_path),
            status="launched",
            backend="process",
            worker_role="self_repair",
        ),
    )

    result = _runner().run_capability(
        "supervisor.project_status",
        inputs={"state_root": str(tmp_path)},
    )

    workers = result["project_state"]["self_repair_workers"]
    assert len(workers) == 1
    worker = workers[0]
    assert worker["record_id"] == "managed-self-repair"
    assert worker["name"] == "desktop-self-repair"
    assert worker["worker_role"] == "self_repair"
    assert worker["supervisor_protocol"] == {
        "status": "done",
        "summary": "已修复 Desktop chat 项目态势读取。",
        "next": "等待主线合并。",
    }
    assert worker["changes"]["status"] == "unknown"
    rendered = json.dumps(result, ensure_ascii=False)
    assert "Isotope self-repair request" not in rendered
    assert "prompt" not in rendered



def test_project_status_capability_includes_latest_self_repair_summary(tmp_path):
    old_workspace = tmp_path / "repo" / ".worktrees" / "supervisor" / "old-repair"
    new_workspace = tmp_path / "repo" / ".worktrees" / "supervisor" / "new-repair"
    old_workspace.mkdir(parents=True)
    new_workspace.mkdir(parents=True)
    old_log_path = tmp_path / "supervisor" / "logs" / "old-repair.log"
    new_log_path = tmp_path / "supervisor" / "logs" / "new-repair.log"
    old_log_path.parent.mkdir(parents=True)
    old_log_path.write_text(
        "\n".join(
            [
                "SUPERVISOR_STATUS: working",
                "SUPERVISOR_SUMMARY: 旧自修复仍在排查。",
                "SUPERVISOR_NEXT: 继续读取上下文。",
            ]
        ),
        encoding="utf-8",
    )
    new_log_path.write_text(
        "\n".join(
            [
                "SUPERVISOR_STATUS: done",
                "SUPERVISOR_SUMMARY: 已补齐最新自修复结果摘要。",
                "SUPERVISOR_NEXT: 等待主线合并。",
            ]
        ),
        encoding="utf-8",
    )
    append_managed_record(
        default_registry_path(tmp_path),
        ManagedCodexRecord(
            record_id="managed-old-repair",
            name="old-repair",
            cwd=str(old_workspace),
            prompt="old private self-repair prompt",
            command=("codex", "exec", "-C", str(old_workspace), "prompt"),
            pid=0,
            started_at="2026-06-04T00:00:00+00:00",
            log_path=str(old_log_path),
            status="launched",
            backend="process",
            worker_role="self_repair",
        ),
    )
    append_managed_record(
        default_registry_path(tmp_path),
        ManagedCodexRecord(
            record_id="managed-new-repair",
            name="new-repair",
            cwd=str(new_workspace),
            prompt="new private self-repair prompt",
            command=("codex", "exec", "-C", str(new_workspace), "prompt"),
            pid=0,
            started_at="2026-06-04T01:00:00+00:00",
            log_path=str(new_log_path),
            status="launched",
            backend="process",
            worker_role="self_repair",
        ),
    )

    result = _runner().run_capability(
        "supervisor.project_status",
        inputs={"state_root": str(tmp_path)},
    )

    latest = result["project_state"]["latest_self_repair"]
    assert latest == {
        "record_id": "managed-new-repair",
        "name": "new-repair",
        "worker_role": "self_repair",
        "registry_status": "launched",
        "started_at": "2026-06-04T01:00:00+00:00",
        "cwd": str(new_workspace),
        "cwd_exists": True,
        "branch": "supervisor/new-repair",
        "protocol_status": "done",
        "summary": "已补齐最新自修复结果摘要。",
        "next": "等待主线合并。",
        "changes_status": "unknown",
        "changes_summary": "loop 快速状态未读取 diff",
        "test_status": "skipped",
        "test_passed": None,
        "test_exit_code": None,
        "recommendation": "review_then_merge_candidate",
        "decision_summary": "worker 已完成且有本地改动；建议先复查 diff 并跑验证，通过后再人工合并。",
        "merge_suitable": True,
        "continue_or_split_task": False,
        "risk_level": "medium",
    }
    rendered = json.dumps(result, ensure_ascii=False)
    assert "new private self-repair prompt" not in rendered
    assert "old private self-repair prompt" not in rendered



def test_project_status_capability_includes_open_capability_gaps(tmp_path):
    gap_dir = tmp_path / "supervisor" / "capability-gaps"
    gap_dir.mkdir(parents=True)
    (gap_dir / "gap_open.json").write_text(
        json.dumps(
            {
                "kind": "capability_gap",
                "gap_id": "gap_open",
                "status": "recorded",
                "missing_capability_kind": "skills.mcp.install",
                "reason": "需要安装 skills MCP，但当前没有安全安装能力。",
                "needed_context": ["skills registry", "mcp config"],
                "suggested_next_capability": "isotope.self_repair",
                "source_entrypoint": "desktop_chat",
                "user_goal": "private user request should not be projected",
                "created_at": "2026-06-04T02:00:00Z",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (gap_dir / "gap_resolved.json").write_text(
        json.dumps(
            {
                "kind": "capability_gap",
                "gap_id": "gap_resolved",
                "status": "resolved",
                "missing_capability_kind": "old.gap",
                "reason": "已解决的缺口不应出现在 open 列表。",
                "needed_context": [],
                "created_at": "2026-06-04T01:00:00Z",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = _runner().run_capability(
        "supervisor.project_status",
        inputs={"state_root": str(tmp_path)},
    )

    gaps = result["project_state"]["open_capability_gaps"]
    assert gaps == [
        {
            "kind": "capability_gap",
            "gap_id": "gap_open",
            "status": "recorded",
            "missing_capability_kind": "skills.mcp.install",
            "reason": "需要安装 skills MCP，但当前没有安全安装能力。",
            "needed_context": ["skills registry", "mcp config"],
            "suggested_next_capability": "isotope.self_repair",
            "source_entrypoint": "desktop_chat",
            "created_at": "2026-06-04T02:00:00Z",
        }
    ]
    rendered = json.dumps(result, ensure_ascii=False)
    assert "private user request" not in rendered
    assert "gap_resolved" not in rendered



def test_runner_discovers_isotope_self_repair_from_default_catalog():
    runner = _runner()

    assert "isotope.self_repair" in _ids(runner.list_capabilities())
    description = runner.describe_capability("isotope.self_repair")

    assert description["input_contract"]["required"] == [
        "state_root",
        "cwd",
        "user_goal",
        "failure_summary",
    ]
    assert description["input_contract"]["properties"]["gap_id"]["type"] == "string"
    assert "codex_worker_required_for_non_trivial_changes" in description["safety_boundaries"]
    assert "no_auto_merge" in description["safety_boundaries"]



def test_isotope_self_repair_launches_codex_worker_in_isolated_worktree(
    tmp_path, monkeypatch
):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    state_root = tmp_path / ".isotope"
    launched = {}

    def fake_prepare_launch_worktree(*, cwd, target_name, api=None):
        repair_root = (
            tmp_path / "repo" / ".worktrees" / "supervisor" / "desktop-self-repair"
        )
        repair_root.mkdir(parents=True)
        return {
            "enabled": True,
            "source_cwd": str(cwd),
            "cwd": str(repair_root),
            "worktree_root": str(repair_root),
            "branch": "codex/desktop-self-repair",
        }

    class FakeRecord:
        name = "desktop-self-repair"
        record_id = "managed-self-repair"
        pid = 12345
        backend = "process"
        worker_role = "self_repair"
        cwd = str(
            tmp_path / "repo" / ".worktrees" / "supervisor" / "desktop-self-repair"
        )
        log_path = str(tmp_path / "self-repair.log")

    def fake_launch_managed_codex(**kwargs):
        launched.update(kwargs)
        return FakeRecord()

    monkeypatch.setattr(
        "isotope.features.supervisor.self_repair.prepare_launch_worktree",
        fake_prepare_launch_worktree,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.self_repair.launch_managed_codex",
        fake_launch_managed_codex,
    )

    result = _runner().run_capability(
        "isotope.self_repair",
        inputs={
            "state_root": str(state_root),
            "cwd": str(workspace),
            "user_goal": "让 Desktop chat 可以总结项目态势。",
            "failure_summary": "缺少低敏项目状态 capability。",
            "suggested_fix_summary": "新增 supervisor.project_status。",
        },
    )

    assert result["capability_id"] == "isotope.self_repair"
    assert result["status"] == "launched"
    assert result["self_repair"]["managed"]["name"] == "desktop-self-repair"
    assert result["self_repair"]["managed"]["worker_role"] == "self_repair"
    assert result["self_repair"]["worktree"]["enabled"] is True
    assert launched["codex_home"] == state_root
    assert launched["cwd"].name == "desktop-self-repair"
    assert launched["worker_role"] == "self_repair"
    assert "不要合入 main" in launched["prompt"]
    assert "让 Desktop chat 可以总结项目态势。" in launched["prompt"]



def test_isotope_self_repair_can_include_capability_gap_context(
    tmp_path, monkeypatch
):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    state_root = tmp_path / ".isotope"
    gap_dir = state_root / "supervisor" / "capability-gaps"
    gap_dir.mkdir(parents=True)
    (gap_dir / "gap_skills.json").write_text(
        json.dumps(
            {
                "kind": "capability_gap",
                "gap_id": "gap_skills",
                "status": "recorded",
                "missing_capability_kind": "skills.mcp.install",
                "reason": "需要安装 skills MCP，但当前没有安全安装能力。",
                "needed_context": ["skills registry", "mcp config"],
                "suggested_next_capability": "isotope.self_repair",
                "source_entrypoint": "desktop_chat",
                "user_goal": "private gap user goal should not enter worker prompt",
                "created_at": "2026-06-04T02:00:00Z",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    launched = {}

    def fake_prepare_launch_worktree(*, cwd, target_name, api=None):
        repair_root = workspace / ".worktrees" / "supervisor" / target_name
        repair_root.mkdir(parents=True)
        return {
            "enabled": True,
            "source_cwd": str(cwd),
            "cwd": str(repair_root),
            "worktree_root": str(repair_root),
            "branch": f"codex/{target_name}",
        }

    class FakeRecord:
        name = "desktop-self-repair"
        record_id = "managed-self-repair"
        pid = 12345
        backend = "process"
        worker_role = "self_repair"
        cwd = str(workspace / ".worktrees" / "supervisor" / "desktop-self-repair")
        log_path = str(tmp_path / "self-repair.log")

    def fake_launch_managed_codex(**kwargs):
        launched.update(kwargs)
        return FakeRecord()

    monkeypatch.setattr(
        "isotope.features.supervisor.self_repair.prepare_launch_worktree",
        fake_prepare_launch_worktree,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.self_repair.launch_managed_codex",
        fake_launch_managed_codex,
    )

    result = _runner().run_capability(
        "isotope.self_repair",
        inputs={
            "state_root": str(state_root),
            "cwd": str(workspace),
            "user_goal": "修复 skills MCP 安装能力。",
            "failure_summary": "模型报告了 skills MCP 安装能力缺口。",
            "gap_id": "gap_skills",
        },
    )

    assert result["self_repair"]["capability_gap"]["gap_id"] == "gap_skills"
    assert "gap_skills" in launched["prompt"]
    assert "skills.mcp.install" in launched["prompt"]
    assert "需要安装 skills MCP" in launched["prompt"]
    assert "skills registry" in launched["prompt"]
    assert "private gap user goal" not in launched["prompt"]



def test_isotope_self_repair_blocks_when_isolated_worktree_is_unavailable(
    tmp_path, monkeypatch
):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    launched = False

    def fake_prepare_launch_worktree(*, cwd, target_name, api=None):
        return {
            "enabled": False,
            "source_cwd": str(cwd),
            "cwd": str(cwd),
            "reason": "not_git_repo",
        }

    def fake_launch_managed_codex(**kwargs):
        nonlocal launched
        launched = True
        raise AssertionError("must not launch without an isolated worktree")

    monkeypatch.setattr(
        "isotope.features.supervisor.self_repair.prepare_launch_worktree",
        fake_prepare_launch_worktree,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.self_repair.launch_managed_codex",
        fake_launch_managed_codex,
    )

    result = _runner().run_capability(
        "isotope.self_repair",
        inputs={
            "state_root": str(tmp_path / ".isotope"),
            "cwd": str(workspace),
            "user_goal": "修复能力缺口。",
            "failure_summary": "无法创建隔离 worktree。",
        },
    )

    assert result["status"] == "blocked"
    assert result["self_repair"]["status"] == "blocked"
    assert result["self_repair"]["reason"] == "worktree_unavailable"
    assert result["self_repair"]["worktree"]["enabled"] is False
    assert launched is False



def test_runner_discovers_supervisor_worker_review_from_default_catalog():
    runner = _runner()

    assert "supervisor.worker_review" in _ids(runner.list_capabilities())
    search = runner.search_capabilities(query="worker-review")

    assert _ids(search["capabilities"]) == ["supervisor.worker_review"]
    description = runner.describe_capability("supervisor.worker_review")
    assert description["input_contract"]["required"] == ["state_root"]
    assert "codex_home" not in description["input_contract"]["properties"]
    assert "workspace_state_projection" in description["safety_boundaries"]
    assert "worker_decision_handoff" in description["safety_boundaries"]
    assert "worker_lifecycle_cleanup_handoff" in description["safety_boundaries"]



def test_supervisor_worker_review_manifest_uses_decision_handoff_language():
    description = _runner().describe_capability("supervisor.worker_review")
    manifest_text = json.dumps(description, ensure_ascii=False)

    forbidden_terms = [
        "read" + "_snapshot",
        "inspection " + "mode",
        "no" + "_merge" + "_or" + "_cleanup",
        "只读" + "扫描",
        "不" + "执行",
    ]

    assert "worker decisions" in description["description"]
    assert "worker_decision_handoff" in description["safety_boundaries"]
    for term in forbidden_terms:
        assert term not in manifest_text



def test_runner_discovers_supervisor_goal_plan_from_default_catalog():
    runner = _runner()

    assert "supervisor.goal_plan" in _ids(runner.list_capabilities())
    search = runner.search_capabilities(query="goal plan")

    assert "supervisor.goal_plan" in _ids(search["capabilities"])
    description = runner.describe_capability("supervisor.goal_plan")
    assert description["input_contract"]["required"] == ["state_root", "cwd", "goal"]
    assert "codex_home" not in description["input_contract"]["properties"]
    assert "reuses_goal_planner" in description["safety_boundaries"]
    assert "write_requires_explicit_flag" in description["safety_boundaries"]



def test_runner_discovers_supervisor_integration_review_from_default_catalog():
    runner = _runner()

    assert "supervisor.integration_review" in _ids(runner.list_capabilities())
    search = runner.search_capabilities(query="integration-review")

    assert _ids(search["capabilities"]) == ["supervisor.integration_review"]
    description = runner.describe_capability("supervisor.integration_review")
    assert description["input_contract"]["required"] == ["state_root"]
    assert "codex_home" not in description["input_contract"]["properties"]
    assert "workspace_state_projection" in description["safety_boundaries"]
    assert "merge_dispatch_handoff" in description["safety_boundaries"]
    assert "worker_lifecycle_cleanup_handoff" in description["safety_boundaries"]



def test_supervisor_integration_review_manifest_uses_execution_handoff_language():
    description = _runner().describe_capability("supervisor.integration_review")
    manifest_text = json.dumps(description, ensure_ascii=False)

    forbidden_terms = [
        "read" + "_snapshot",
        "inspection " + "mode",
        "no" + "_merge" + "_push" + "_or" + "_cleanup",
        "只读" + "扫描",
        "不" + "执行",
    ]

    assert "merge readiness" in description["description"]
    assert "merge_dispatch_handoff" in description["safety_boundaries"]
    for term in forbidden_terms:
        assert term not in manifest_text



