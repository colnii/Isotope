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


def _git(cwd, *args):
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=True,
    )


def _git_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test User")
    (repo / "app.py").write_text("print('old')\n", encoding="utf-8")
    _git(repo, "add", "app.py")
    _git(repo, "commit", "-m", "initial")
    return repo


def _walk_mapping(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_mapping(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_mapping(child)


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


def test_capability_runner_module_exists():
    module = _runner_module()

    assert module.__name__ == "isotope.capabilities.runner"


def test_runner_rejects_malformed_catalog_dependency():
    with pytest.raises(ValueError, match="catalog"):
        _runner_module().CapabilityRunner(catalog=object())


def test_runner_list_uses_capability_catalog_as_source_of_truth():
    catalog = CapabilityCatalog(
        capabilities=[
            _capability("artifact.review", "product_candidate"),
            _capability("external.snapshot.review", "prototype"),
            _capability("hidden.diagnostic", "diagnostic"),
        ]
    )

    assert _ids(_runner(catalog=catalog).list_capabilities()) == [
        "artifact.review",
        "external.snapshot.review",
    ]


def test_runner_discovers_extension_entrypoint_capabilities():
    runner = _runner()

    ids = _ids(runner.list_capabilities())

    assert "skills.search" in ids
    assert "skills.describe" in ids
    assert "mcp.servers.list" in ids
    assert "mcp.tools.search" in ids
    assert "mcp.tool.call" in ids


def test_runner_executes_skills_search_with_explicit_roots(tmp_path):
    root = tmp_path / "skills"
    skill_dir = root / "frontend"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: frontend-design\n"
        "description: Build production-grade frontend interfaces.\n"
        "---\n\n"
        "# frontend-design\n",
        encoding="utf-8",
    )
    runner = _runner()

    result = runner.run_capability(
        "skills.search",
        inputs={"roots": [str(root)], "query": "frontend"},
    )

    assert result["status"] == "completed"
    assert result["runner_kind"] == "extension_skill_registry"
    assert result["skills"][0]["skill_id"] == "frontend-design"
    assert "body" not in result["skills"][0]


def test_runner_executes_skills_describe_with_bounded_body(tmp_path):
    root = tmp_path / "skills"
    skill_dir = root / "docx"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: llm2docx\n"
        "description: Fill Word templates.\n"
        "---\n\n"
        "# llm2docx\n\n"
        "Use this skill for docx work.\n",
        encoding="utf-8",
    )
    runner = _runner()

    result = runner.run_capability(
        "skills.describe",
        inputs={"roots": [str(root)], "skill_id": "llm2docx", "max_body_chars": 40},
    )

    assert result["status"] == "completed"
    assert result["runner_kind"] == "extension_skill_registry"
    assert result["skill"]["skill_id"] == "llm2docx"
    assert "Use this skill" in result["body"]


def test_runner_plans_mcp_capabilities_as_missing_inputs():
    runner = _runner()

    plan = runner.plan_capability_run("mcp.tool.call", inputs={})

    assert plan["status"] == "missing_inputs"
    assert plan["missing_inputs"] == ["server_id", "tool_name"]
    assert plan["can_launch"] is False


def test_runner_rejects_mcp_tool_call_without_config(monkeypatch):
    monkeypatch.delenv("ISOTOPE_MCP_SERVERS_JSON", raising=False)
    runner = _runner()

    with pytest.raises(ValueError, match="unknown MCP server"):
        runner.run_capability(
            "mcp.tool.call",
            inputs={"server_id": "missing", "tool_name": "echo", "arguments": {}},
        )


def test_runner_executes_mcp_tool_call_from_explicit_env_config(monkeypatch):
    fixture_server = (
        Path(__file__).resolve().parents[2] / "fixtures" / "mcp_echo_server.py"
    )
    monkeypatch.setenv(
        "ISOTOPE_MCP_SERVERS_JSON",
        json.dumps(
            {
                "echo": {
                    "command": sys.executable,
                    "args": [str(fixture_server)],
                    "enabled": True,
                    "allowed_tools": ["echo"],
                }
            }
        ),
    )
    runner = _runner()

    result = runner.run_capability(
        "mcp.tool.call",
        inputs={
            "server_id": "echo",
            "tool_name": "echo",
            "arguments": {"text": "hello from runner"},
        },
    )

    assert result["status"] == "completed"
    assert result["runner_kind"] == "extension_mcp_client"
    assert result["server_id"] == "echo"
    assert result["tool_name"] == "echo"
    assert result["structured_content"] == {"echo": "hello from runner"}
    assert result["is_error"] is False


def test_runner_describe_returns_public_metadata_catalog_metadata():
    description = _runner().describe_capability("artifact.review")

    assert description["capability_id"] == "artifact.review"
    assert description["shelf"] == "product_candidate"
    assert "input_contract" in description
    assert "output_contract" in description
    json.dumps(description)
    for mapping in _walk_mapping(description):
        assert FORBIDDEN_RESULT_KEYS.isdisjoint(mapping)


def test_runner_discovers_supervisor_request_context_from_default_catalog():
    runner = _runner()

    assert "supervisor.request_context" in _ids(runner.list_capabilities())
    search = runner.search_capabilities(query="request_context")

    assert _ids(search["capabilities"]) == ["supervisor.request_context"]
    description = runner.describe_capability("supervisor.request_context")
    assert description["input_contract"]["required"] == ["state_root", "cwd", "query"]
    assert "codex_home" not in description["input_contract"]["properties"]
    assert "workspace_read_snapshot" in description["safety_boundaries"]
    assert "writes_existing_supervisor_context_store" in description["safety_boundaries"]


def test_runner_discovers_supervisor_project_status_from_default_catalog():
    runner = _runner()

    ids = _ids(runner.list_capabilities())
    assert "supervisor.project_status" in ids
    description = runner.describe_capability("supervisor.project_status")

    assert description["input_contract"]["required"] == ["state_root"]
    assert description["input_contract"]["properties"]["state_root"]["type"] == "string"
    assert "project_state_summary" in description["output_contract"]["fields"]
    assert "read_only_state_projection" in description["safety_boundaries"]


def test_project_status_capability_returns_low_sensitive_snapshot_summary(tmp_path):
    runner = _runner()

    result = runner.run_capability(
        "supervisor.project_status",
        inputs={"state_root": str(tmp_path)},
    )

    assert result["kind"] == "capability_run_result"
    assert result["capability_id"] == "supervisor.project_status"
    assert result["status"] == "completed"
    summary = result["project_state_summary"]
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

    workers = result["project_state_summary"]["self_repair_workers"]
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

    latest = result["project_state_summary"]["latest_self_repair"]
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
    assert "workspace_read_snapshot" in description["safety_boundaries"]
    assert "no_merge_or_cleanup" in description["safety_boundaries"]


def test_memory_recall_capability_is_registered_as_readonly_product_candidate():
    runner = _runner()

    assert "memory.recall" in _ids(runner.list_capabilities())
    description = runner.describe_capability("memory.recall")
    assert description["shelf"] == "product_candidate"
    assert description["network_required"] is False
    assert description["input_contract"]["required"] == ["root", "query"]
    assert description["input_contract"]["properties"]["root"]["x-system-input"] is True


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
    assert "workspace_read_snapshot" in description["safety_boundaries"]
    assert "no_merge_push_or_cleanup" in description["safety_boundaries"]


def test_runner_discovers_memory_query_from_default_catalog():
    runner = _runner()

    assert "memory.query" in _ids(runner.list_capabilities())
    search = runner.search_capabilities(query="memory")

    assert "memory.query" in _ids(search["capabilities"])
    description = runner.describe_capability("memory.query")
    assert description["input_contract"]["required"] == ["root", "query", "run_id"]
    assert "memory_query_grant_gated" in description["safety_boundaries"]
    assert "memory_record_refs_expandable" in description["safety_boundaries"]


def test_runner_discovers_memory_promotion_preview_from_default_catalog():
    runner = _runner()

    assert "memory.promotion.preview" in _ids(runner.list_capabilities())
    search = runner.search_capabilities(query="promotion")

    assert "memory.promotion.preview" in _ids(search["capabilities"])
    description = runner.describe_capability("memory.promotion.preview")
    assert description["input_contract"]["required"] == [
        "run_id",
        "agent_id",
        "thread_id",
        "candidate",
    ]
    assert "proposal_payload" in description["safety_boundaries"]
    assert "no_memory_write" in description["safety_boundaries"]


def test_runner_discovers_screen_report_from_default_catalog():
    runner = _runner()

    assert "screen.report" in _ids(runner.list_capabilities())
    search = runner.search_capabilities(query="screen report")

    assert "screen.report" in _ids(search["capabilities"])
    description = runner.describe_capability("screen.report")
    assert description["input_contract"]["required"] == ["root", "run_id"]
    assert "screen_artifact_read_snapshot" in description["safety_boundaries"]
    assert "public_result_metadata" in description["safety_boundaries"]


def test_runner_discovers_screen_observe_from_default_catalog():
    runner = _runner()

    assert "screen.observe" in _ids(runner.list_capabilities())
    search = runner.search_capabilities(query="screen observe")

    assert "screen.observe" in _ids(search["capabilities"])
    description = runner.describe_capability("screen.observe")
    assert description["input_contract"]["required"] == ["target_selector"]
    assert "policy_gated_screen_observe" in description["safety_boundaries"]
    assert "screen_report_artifact" in description["safety_boundaries"]
    assert "no_screenshot_content_in_events" in description["safety_boundaries"]
    assert "screenshot_content_for_model_observation" in description["safety_boundaries"]


def test_runner_discovers_research_search_from_default_catalog():
    runner = _runner()

    assert "research.search" in _ids(runner.list_capabilities())
    search = runner.search_capabilities(query="research search")

    assert _ids(search["capabilities"]) == ["research.search"]
    description = runner.describe_capability("research.search")
    assert description["input_contract"]["required"] == [
        "root",
        "query",
    ]
    assert set(description["input_contract"]["properties"]) == {"root", "query"}
    assert "reuses_research_flow" in description["safety_boundaries"]
    assert "runtime_provider_policy" in description["safety_boundaries"]


def test_runner_discovers_research_promote_from_default_catalog():
    runner = _runner()

    assert "research.promote" in _ids(runner.list_capabilities())
    search = runner.search_capabilities(query="research promote")

    assert _ids(search["capabilities"]) == ["research.promote"]
    description = runner.describe_capability("research.promote")
    assert description["input_contract"]["required"] == [
        "root",
        "run_id",
        "artifact_id",
        "agent_id",
        "thread_id",
    ]
    assert description["input_contract"]["properties"]["scope"]["enum"] == [
        "thread",
        "run",
        "session",
    ]
    assert "reuses_memory_promotion_boundary" in description["safety_boundaries"]
    assert "proposal_only_no_memory_write" in description["safety_boundaries"]


def test_runner_discovers_coding_task_preview_from_default_catalog():
    runner = _runner()

    assert "coding_task.preview" in _ids(runner.list_capabilities())
    search = runner.search_capabilities(query="native coding")

    assert "coding_task.preview" in _ids(search["capabilities"])
    description = runner.describe_capability("coding_task.preview")
    assert description["input_contract"]["required"] == ["root", "cwd", "goal"]
    assert description["input_contract"]["properties"]["allowed_paths"]["type"] == "array"
    assert (
        description["input_contract"]["properties"]["verification_commands"]["type"]
        == "array"
    )
    assert "no_codex_delegation" in description["safety_boundaries"]
    assert "proposal_plan_no_workspace_write" in description["safety_boundaries"]


def test_runner_runs_coding_task_preview_without_side_effects(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    root = tmp_path / "state"

    result = _runner().run_capability(
        "coding_task.preview",
        inputs={
            "root": str(root),
            "cwd": str(workspace),
            "goal": "Add a native code edit action.",
            "allowed_paths": ["src/isotope/capabilities"],
            "verification_commands": ["pytest tests/unit/capabilities -q"],
        },
    )

    assert result["kind"] == "capability_run_result"
    assert result["capability_id"] == "coding_task.preview"
    assert result["status"] == "completed"
    assert result["runner_kind"] == "deterministic_preview"
    assert result["preview"]["goal"] == "Add a native code edit action."
    assert result["preview"]["cwd_status"] == "exists"
    assert result["preview"]["execution_mode"] == "proposal_plan"
    assert result["preview"]["native_coding_requirements"] == [
        "policy_granted_writable_workspace",
        "controlled_code_read_search",
        "structured_patch_application",
        "allowlisted_test_execution",
        "artifact_backed_diff_and_changed_files",
        "optional_vcs_adapter",
    ]
    assert result["preview"]["blocked_capabilities"] == []
    assert not list(root.rglob("*"))


def test_coding_task_preview_rejects_malformed_path_lists(tmp_path):
    with pytest.raises(ValueError, match="allowed_paths"):
        _runner().run_capability(
            "coding_task.preview",
            inputs={
                "root": str(tmp_path / "state"),
                "cwd": str(tmp_path),
                "goal": "Edit code.",
                "allowed_paths": "src",
            },
        )


def test_coding_task_preview_reports_missing_cwd_without_creating_it(tmp_path):
    missing = tmp_path / "missing"

    result = _runner().run_capability(
        "coding_task.preview",
        inputs={
            "root": str(tmp_path / "state"),
            "cwd": str(missing),
            "goal": "Edit code.",
        },
    )

    assert result["preview"]["cwd_status"] == "missing"
    assert not missing.exists()


def test_coding_task_preview_plan_stops_when_required_inputs_are_missing():
    plan = _runner().plan_capability_run(
        "coding_task.preview",
        inputs={"cwd": "/tmp/project"},
    )

    assert plan["can_launch"] is False
    assert plan["status"] == "missing_inputs"
    assert plan["runner_kind"] == "deterministic_preview"
    assert plan["missing_inputs"] == ["root", "goal"]
    assert plan["scenario"] is None


def test_coding_task_preview_plan_is_launchable_with_required_inputs(tmp_path):
    plan = _runner().plan_capability_run(
        "coding_task.preview",
        inputs={
            "root": str(tmp_path / "state"),
            "cwd": str(tmp_path),
            "goal": "Preview native coding.",
        },
    )

    assert plan["can_launch"] is True
    assert plan["status"] == "launchable"
    assert plan["runner_kind"] == "deterministic_preview"
    assert plan["blocking_reasons"] == []
    assert "proposal_plan_no_workspace_write" in plan["safety_boundaries"]


def test_runner_discovers_coding_task_execute_from_default_catalog():
    runner = _runner()

    assert "coding_task.execute" in _ids(runner.list_capabilities())
    assert "coding_task.execute" in _ids(
        runner.search_capabilities(query="native coding execute")["capabilities"]
    )

    description = runner.describe_capability("coding_task.execute")
    assert description["input_contract"]["required"] == [
        "root",
        "cwd",
        "workspace_id",
        "goal",
        "patch",
        "argv",
        "run_id",
        "execution_id",
    ]
    assert "no_codex_delegation" in description["safety_boundaries"]
    assert "limited_step_count" in description["safety_boundaries"]


def test_runner_discovers_coding_task_run_from_default_catalog():
    runner = _runner()

    assert "coding_task.run" in _ids(runner.list_capabilities())
    description = runner.describe_capability("coding_task.run")

    assert description["input_contract"]["required"] == ["goal"]
    properties = description["input_contract"]["properties"]
    assert properties["goal"]["type"] == "string"
    for name in ("root", "cwd", "run_id", "execution_id", "workspace_id"):
        assert properties[name]["x-system-input"] is True
    assert "uses_existing_agent_loop" in description["safety_boundaries"]
    assert "does_not_replace_coding_task_execute" in description["safety_boundaries"]


def test_runner_discovers_coding_task_apply_reviewed_diff_from_default_catalog():
    runner = _runner()

    assert "coding_task.apply_reviewed_diff" in _ids(runner.list_capabilities())
    description = runner.describe_capability("coding_task.apply_reviewed_diff")

    assert description["input_contract"]["required"] == [
        "root",
        "cwd",
        "workspace_id",
        "expected_source_digests",
    ]
    properties = description["input_contract"]["properties"]
    assert properties["root"]["x-system-input"] is True
    assert properties["cwd"]["x-system-input"] is True
    assert properties["workspace_id"]["x-system-input"] is True
    assert properties["expected_source_digests"]["x-system-input"] is True
    assert properties["review_handle_id"]["type"] == "string"
    assert "source_workspace_write_requires_explicit_apply" in description["safety_boundaries"]
    assert "source_digest_conflict_guard" in description["safety_boundaries"]


def test_runner_rejects_direct_coding_task_run_execution(tmp_path):
    with pytest.raises(
        ValueError,
        match="coding_task.run must be routed through Supervisor agent loop",
    ):
        _runner().run_capability(
            "coding_task.run",
            root_path=tmp_path,
            inputs={"goal": "Change src/app.py value to 2."},
        )


def test_runner_executes_native_coding_task_in_isolated_workspace(tmp_path):
    source = tmp_path / "repo"
    (source / "src").mkdir(parents=True)
    (source / "src" / "app.py").write_text("value = 1\n", encoding="utf-8")
    root = tmp_path / "state"

    result = _runner().run_capability(
        "coding_task.execute",
        inputs={
            "root": str(root),
            "cwd": str(source),
            "workspace_id": "workspace_native_coding_execute",
            "goal": "Change value to 2.",
            "patch": (
                "--- a/src/app.py\n"
                "+++ b/src/app.py\n"
                "@@ -1 +1 @@\n"
                "-value = 1\n"
                "+value = 2\n"
            ),
            "argv": [
                "python3",
                "-c",
                "from pathlib import Path; assert Path('src/app.py').read_text() == 'value = 2\\n'",
            ],
            "allowed_commands": ["python3"],
            "run_id": "run_native_coding",
            "execution_id": "execution_native_coding",
            "include_paths": ["src"],
        },
    )

    execution = result["coding_execution"]
    artifacts = ArtifactStore(root).list_artifacts("run_native_coding")
    workspace_file = (
        root
        / "workspaces"
        / "workspace_native_coding_execute"
        / "src"
        / "app.py"
    )
    assert result["kind"] == "capability_run_result"
    assert result["capability_id"] == "coding_task.execute"
    assert result["status"] == "completed"
    assert result["runner_kind"] == "deterministic_local"
    assert execution["status"] == "verified"
    assert execution["workspace_id"] == "workspace_native_coding_execute"
    assert execution["step_count"] == 5
    assert execution["source_workspace_write"] == "not_performed"
    assert execution["patch_result"]["status"] == "applied"
    assert execution["verification"]["status"] == "passed"
    assert execution["artifact_refs"]["changed_files"]["ref_type"] == "artifact"
    assert execution["artifact_refs"]["diff_summary"]["ref_type"] == "artifact"
    assert sorted(artifact.artifact_type for artifact in artifacts) == [
        "native_coding.changed_files",
        "native_coding.diff_summary",
        "native_coding.reviewed_apply_request",
    ]
    reviewed_apply = execution["reviewed_apply"]
    assert reviewed_apply["workspace_id"] == "workspace_native_coding_execute"
    assert reviewed_apply["expected_source_digests"]["src/app.py"]
    assert reviewed_apply["review_handle_id"]
    assert reviewed_apply["review_handle_ref"]["ref_type"] == "artifact"
    handle_content = json.loads(
        ArtifactStore(root).get_content(reviewed_apply["review_handle_id"])
    )
    assert handle_content == {
        "kind": "native_coding_reviewed_apply_request",
        "workspace_id": "workspace_native_coding_execute",
        "changed_files": ["src/app.py"],
        "expected_changed_files": ["src/app.py"],
        "expected_source_digests": reviewed_apply["expected_source_digests"],
        "include_paths": ["src"],
        "content_policy": "digest_and_path_only",
    }
    assert (source / "src" / "app.py").read_text(encoding="utf-8") == "value = 1\n"
    assert workspace_file.read_text(encoding="utf-8") == "value = 2\n"
    assert "patch" not in execution


def test_runner_applies_reviewed_native_coding_workspace_to_source(tmp_path):
    source = tmp_path / "repo"
    (source / "src").mkdir(parents=True)
    (source / "src" / "app.py").write_text("value = 1\n", encoding="utf-8")
    root = tmp_path / "state"
    execute_result = _runner().run_capability(
        "coding_task.execute",
        inputs={
            "root": str(root),
            "cwd": str(source),
            "workspace_id": "workspace_native_apply",
            "goal": "Change value to 2.",
            "patch": (
                "--- a/src/app.py\n"
                "+++ b/src/app.py\n"
                "@@ -1 +1 @@\n"
                "-value = 1\n"
                "+value = 2\n"
            ),
            "argv": [
                "python3",
                "-c",
                "from pathlib import Path; assert Path('src/app.py').read_text() == 'value = 2\\n'",
            ],
            "allowed_commands": ["python3"],
            "run_id": "run_native_apply",
            "execution_id": "execution_native_apply",
            "include_paths": ["src"],
        },
    )

    reviewed_apply = execute_result["coding_execution"]["reviewed_apply"]
    result = _runner().run_capability(
        "coding_task.apply_reviewed_diff",
        inputs={
            "root": str(root),
            "cwd": str(source),
            "workspace_id": reviewed_apply["workspace_id"],
            "expected_source_digests": reviewed_apply["expected_source_digests"],
            "include_paths": ["src"],
        },
    )

    applied = result["reviewed_apply"]
    assert result["kind"] == "capability_run_result"
    assert result["capability_id"] == "coding_task.apply_reviewed_diff"
    assert result["status"] == "completed"
    assert applied["status"] == "applied"
    assert applied["source_workspace_write"] == "performed"
    assert applied["applied_files"] == ["src/app.py"]
    assert (source / "src" / "app.py").read_text(encoding="utf-8") == "value = 2\n"
    assert "value = 2" not in json.dumps(applied, ensure_ascii=False)


def test_runner_applies_reviewed_native_coding_workspace_by_review_handle(tmp_path):
    source = tmp_path / "repo"
    (source / "src").mkdir(parents=True)
    (source / "src" / "app.py").write_text("value = 1\n", encoding="utf-8")
    root = tmp_path / "state"
    execute_result = _runner().run_capability(
        "coding_task.execute",
        inputs={
            "root": str(root),
            "cwd": str(source),
            "workspace_id": "workspace_native_apply_handle",
            "goal": "Change value to 2.",
            "patch": (
                "--- a/src/app.py\n"
                "+++ b/src/app.py\n"
                "@@ -1 +1 @@\n"
                "-value = 1\n"
                "+value = 2\n"
            ),
            "argv": [
                "python3",
                "-c",
                "from pathlib import Path; assert Path('src/app.py').read_text() == 'value = 2\\n'",
            ],
            "allowed_commands": ["python3"],
            "run_id": "run_native_apply_handle",
            "execution_id": "execution_native_apply_handle",
            "include_paths": ["src"],
        },
    )

    result = _runner().run_capability(
        "coding_task.apply_reviewed_diff",
        inputs={
            "root": str(root),
            "cwd": str(source),
            "review_handle_id": execute_result["coding_execution"]["reviewed_apply"][
                "review_handle_id"
            ],
        },
    )

    applied = result["reviewed_apply"]
    assert applied["status"] == "applied"
    assert applied["review_handle_id"]
    assert applied["applied_files"] == ["src/app.py"]
    assert (source / "src" / "app.py").read_text(encoding="utf-8") == "value = 2\n"
    assert "value = 2" not in json.dumps(applied, ensure_ascii=False)


def test_reviewed_native_coding_apply_blocks_source_conflict_without_write(tmp_path):
    source = tmp_path / "repo"
    (source / "src").mkdir(parents=True)
    (source / "src" / "app.py").write_text("value = 1\n", encoding="utf-8")
    root = tmp_path / "state"
    execute_result = _runner().run_capability(
        "coding_task.execute",
        inputs={
            "root": str(root),
            "cwd": str(source),
            "workspace_id": "workspace_native_apply_conflict",
            "goal": "Change value to 2.",
            "patch": (
                "--- a/src/app.py\n"
                "+++ b/src/app.py\n"
                "@@ -1 +1 @@\n"
                "-value = 1\n"
                "+value = 2\n"
            ),
            "argv": [
                "python3",
                "-c",
                "from pathlib import Path; assert Path('src/app.py').read_text() == 'value = 2\\n'",
            ],
            "allowed_commands": ["python3"],
            "run_id": "run_native_apply_conflict",
            "execution_id": "execution_native_apply_conflict",
            "include_paths": ["src"],
        },
    )
    (source / "src" / "app.py").write_text("value = 9\n", encoding="utf-8")

    result = _runner().run_capability(
        "coding_task.apply_reviewed_diff",
        inputs={
            "root": str(root),
            "cwd": str(source),
            "workspace_id": "workspace_native_apply_conflict",
            "expected_source_digests": execute_result["coding_execution"]["reviewed_apply"][
                "expected_source_digests"
            ],
            "include_paths": ["src"],
        },
    )

    applied = result["reviewed_apply"]
    assert applied["status"] == "blocked"
    assert applied["blocked_reason"] == "source_conflict"
    assert applied["source_workspace_write"] == "not_performed"
    assert (source / "src" / "app.py").read_text(encoding="utf-8") == "value = 9\n"


def test_reviewed_native_coding_apply_blocks_deletions_without_write(tmp_path):
    source = tmp_path / "repo"
    (source / "src").mkdir(parents=True)
    (source / "src" / "delete.py").write_text("delete me\n", encoding="utf-8")
    root = tmp_path / "state"
    workspace_root = root / "workspaces" / "workspace_native_apply_delete" / "src"
    workspace_root.mkdir(parents=True)

    result = _runner().run_capability(
        "coding_task.apply_reviewed_diff",
        inputs={
            "root": str(root),
            "cwd": str(source),
            "workspace_id": "workspace_native_apply_delete",
            "expected_source_digests": {"src/delete.py": "present"},
            "include_paths": ["src"],
        },
    )

    applied = result["reviewed_apply"]
    assert applied["status"] == "blocked"
    assert applied["blocked_reason"] == "deletion_not_supported"
    assert (source / "src" / "delete.py").is_file()


def test_coding_task_execute_plan_stops_when_required_inputs_are_missing():
    plan = _runner().plan_capability_run(
        "coding_task.execute",
        inputs={"cwd": "/tmp/project", "goal": "Edit code."},
    )

    assert plan["can_launch"] is False
    assert plan["status"] == "missing_inputs"
    assert plan["runner_kind"] == "deterministic_local"
    assert plan["missing_inputs"] == [
        "root",
        "workspace_id",
        "patch",
        "argv",
        "run_id",
        "execution_id",
    ]
    assert plan["scenario"] is None


def test_runner_discovers_workspace_isolated_rw_from_default_catalog():
    runner = _runner()

    assert "workspace.isolated_rw" in _ids(runner.list_capabilities())
    search = runner.search_capabilities(query="isolated writable workspace")

    assert "workspace.isolated_rw" in _ids(search["capabilities"])
    description = runner.describe_capability("workspace.isolated_rw")
    assert description["input_contract"]["required"] == ["root", "cwd", "workspace_name"]
    assert description["input_contract"]["properties"]["allowed_paths"]["type"] == "array"
    assert "proposal_only_no_filesystem_write" in description["safety_boundaries"]
    assert "path_traversal_rejected" in description["safety_boundaries"]


def test_runner_runs_workspace_isolated_rw_proposal_without_creating_workspace(tmp_path):
    source = tmp_path / "repo"
    source.mkdir()
    root = tmp_path / "state"

    result = _runner().run_capability(
        "workspace.isolated_rw",
        inputs={
            "root": str(root),
            "cwd": str(source),
            "workspace_name": "Native Coding Slice 2!",
            "allowed_paths": ["src/isotope/capabilities", "tests/unit/capabilities"],
            "forbidden_paths": ["src/isotope/features/supervisor"],
        },
    )

    proposal = result["workspace_proposal"]
    assert result["kind"] == "capability_run_result"
    assert result["capability_id"] == "workspace.isolated_rw"
    assert result["status"] == "completed"
    assert result["runner_kind"] == "deterministic_proposal"
    assert proposal["mode"] == "isolated_rw"
    assert proposal["execution_mode"] == "proposal_only"
    assert proposal["workspace_id"] == "workspace_native_coding_slice_2"
    assert proposal["cwd_status"] == "exists"
    assert proposal["root_ref"] == "workspace://workspace_native_coding_slice_2/isolated_rw"
    assert proposal["allowed_paths"] == [
        "src/isotope/capabilities",
        "tests/unit/capabilities",
    ]
    assert proposal["forbidden_paths"] == ["src/isotope/features/supervisor"]
    assert proposal["next_required_capabilities"] == []
    assert not list(root.rglob("*"))


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("allowed_paths", ["/tmp/outside"]),
        ("allowed_paths", ["src/../secrets"]),
        ("forbidden_paths", ["../outside"]),
        ("forbidden_paths", "src"),
    ],
)
def test_workspace_isolated_rw_rejects_unsafe_paths(tmp_path, field_name, bad_value):
    inputs = {
        "root": str(tmp_path / "state"),
        "cwd": str(tmp_path),
        "workspace_name": "safe-workspace",
    }
    inputs[field_name] = bad_value

    with pytest.raises(ValueError, match=field_name):
        _runner().run_capability("workspace.isolated_rw", inputs=inputs)


def test_workspace_isolated_rw_plan_stops_when_required_inputs_are_missing():
    plan = _runner().plan_capability_run(
        "workspace.isolated_rw",
        inputs={"cwd": "/tmp/project"},
    )

    assert plan["can_launch"] is False
    assert plan["status"] == "missing_inputs"
    assert plan["runner_kind"] == "deterministic_proposal"
    assert plan["missing_inputs"] == ["root", "workspace_name"]
    assert plan["scenario"] is None


def test_runner_discovers_workspace_lease_create_from_default_catalog():
    runner = _runner()

    assert "workspace.lease_create" in _ids(runner.list_capabilities())
    search = runner.search_capabilities(query="workspace lease create")

    assert "workspace.lease_create" in _ids(search["capabilities"])
    description = runner.describe_capability("workspace.lease_create")
    assert description["input_contract"]["required"] == [
        "root",
        "run_id",
        "workspace_id",
        "agent_id",
        "decision_id",
        "proposal_id",
        "execution_id",
    ]
    assert description["input_contract"]["properties"]["mode"]["enum"] == ["isolated_rw"]
    assert "event_candidate_only" in description["safety_boundaries"]
    assert "no_event_append" in description["safety_boundaries"]


def test_runner_runs_workspace_lease_create_event_candidate_without_side_effects(tmp_path):
    root = tmp_path / "state"

    result = _runner().run_capability(
        "workspace.lease_create",
        inputs={
            "root": str(root),
            "run_id": "run_native_coding",
            "workspace_id": "workspace_native_coding_slice_3",
            "agent_id": "agent_supervisor",
            "decision_id": "dec_workspace_001",
            "proposal_id": "prop_workspace_001",
            "execution_id": "exec_workspace_001",
            "mode": "isolated_rw",
        },
    )

    event = result["lease_event"]
    payload = event["payload"]
    assert result["kind"] == "capability_run_result"
    assert result["capability_id"] == "workspace.lease_create"
    assert result["status"] == "completed"
    assert result["runner_kind"] == "deterministic_proposal"
    assert event["event_type"] == "workspace.lease_created"
    assert payload["workspace_id"] == "workspace_native_coding_slice_3"
    assert payload["run_id"] == "run_native_coding"
    assert payload["mode"] == "isolated_rw"
    assert payload["lease_status"] == "created"
    assert payload["bound_to"] == {"agent_id": "agent_supervisor"}
    assert payload["granted_by"] == {"decision_id": "dec_workspace_001"}
    assert payload["created_by"] == {
        "proposal_id": "prop_workspace_001",
        "execution_id": "exec_workspace_001",
    }
    assert payload["provenance"]["grant_basis"]["workspace"] == {"mode": "isolated_rw"}
    assert result["append_required"] is True
    assert not list(root.rglob("*"))


def test_workspace_lease_create_plan_stops_when_required_inputs_are_missing():
    plan = _runner().plan_capability_run(
        "workspace.lease_create",
        inputs={"run_id": "run_native_coding"},
    )

    assert plan["can_launch"] is False
    assert plan["status"] == "missing_inputs"
    assert plan["runner_kind"] == "deterministic_proposal"
    assert plan["missing_inputs"] == [
        "root",
        "workspace_id",
        "agent_id",
        "decision_id",
        "proposal_id",
        "execution_id",
    ]
    assert plan["scenario"] is None


def test_runner_discovers_workspace_materialize_from_default_catalog():
    runner = _runner()

    assert "workspace.materialize" in _ids(runner.list_capabilities())
    search = runner.search_capabilities(query="workspace materialize")

    assert "workspace.materialize" in _ids(search["capabilities"])
    description = runner.describe_capability("workspace.materialize")
    assert description["input_contract"]["required"] == ["root", "cwd", "workspace_id"]
    assert description["input_contract"]["properties"]["include_paths"]["type"] == "array"
    assert "writes_only_under_state_root" in description["safety_boundaries"]
    assert "no_event_append" in description["safety_boundaries"]


def test_runner_materializes_isolated_workspace_under_state_root(tmp_path):
    source = tmp_path / "repo"
    (source / "src").mkdir(parents=True)
    (source / ".git").mkdir()
    (source / ".venv").mkdir()
    (source / "src" / "app.py").write_text("print('native')\n", encoding="utf-8")
    (source / "src" / "skip.py").write_text("skip me\n", encoding="utf-8")
    (source / "README.md").write_text("hello\n", encoding="utf-8")
    (source / ".git" / "config").write_text("private git metadata\n", encoding="utf-8")
    (source / ".venv" / "secret.py").write_text("private venv file\n", encoding="utf-8")
    root = tmp_path / "state"

    result = _runner().run_capability(
        "workspace.materialize",
        inputs={
            "root": str(root),
            "cwd": str(source),
            "workspace_id": "workspace_native_coding_slice_5",
            "include_paths": ["src", "README.md"],
            "forbidden_paths": ["src/skip.py"],
        },
    )

    materialized = result["materialized_workspace"]
    workspace_root = root / "workspaces" / "workspace_native_coding_slice_5"
    assert result["kind"] == "capability_run_result"
    assert result["capability_id"] == "workspace.materialize"
    assert result["status"] == "completed"
    assert result["runner_kind"] == "deterministic_local"
    assert materialized["status"] == "materialized"
    assert materialized["mode"] == "isolated_rw"
    assert materialized["workspace_id"] == "workspace_native_coding_slice_5"
    assert materialized["workspace_root"] == str(workspace_root)
    assert materialized["root_ref"] == "workspace://workspace_native_coding_slice_5/materialized"
    assert materialized["copied_file_count"] == 2
    assert materialized["skipped_file_count"] == 1
    assert materialized["copied_paths"] == ["README.md", "src/app.py"]
    assert materialized["path_policy"]["relative_paths_only"] is True
    assert (workspace_root / "src" / "app.py").read_text(encoding="utf-8") == "print('native')\n"
    assert (workspace_root / "README.md").read_text(encoding="utf-8") == "hello\n"
    assert not (workspace_root / "src" / "skip.py").exists()
    assert not (workspace_root / ".git").exists()
    assert not (workspace_root / ".venv").exists()
    assert (source / "src" / "app.py").read_text(encoding="utf-8") == "print('native')\n"


def test_workspace_materialize_rejects_existing_target_without_overwrite(tmp_path):
    source = tmp_path / "repo"
    source.mkdir()
    root = tmp_path / "state"
    target = root / "workspaces" / "workspace_existing"
    target.mkdir(parents=True)
    marker = target / "marker.txt"
    marker.write_text("keep\n", encoding="utf-8")

    with pytest.raises(FileExistsError, match="workspace target already exists"):
        _runner().run_capability(
            "workspace.materialize",
            inputs={
                "root": str(root),
                "cwd": str(source),
                "workspace_id": "workspace_existing",
            },
        )

    assert marker.read_text(encoding="utf-8") == "keep\n"


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("include_paths", ["../outside"]),
        ("include_paths", ["/tmp/outside"]),
        ("forbidden_paths", ["../secret"]),
        ("forbidden_paths", "src"),
    ],
)
def test_workspace_materialize_rejects_unsafe_paths(tmp_path, field_name, bad_value):
    source = tmp_path / "repo"
    source.mkdir()
    inputs = {
        "root": str(tmp_path / "state"),
        "cwd": str(source),
        "workspace_id": "workspace_safe",
    }
    inputs[field_name] = bad_value

    with pytest.raises(ValueError, match=field_name):
        _runner().run_capability("workspace.materialize", inputs=inputs)


def test_workspace_materialize_plan_stops_when_required_inputs_are_missing():
    plan = _runner().plan_capability_run(
        "workspace.materialize",
        inputs={"cwd": "/tmp/project"},
    )

    assert plan["can_launch"] is False
    assert plan["status"] == "missing_inputs"
    assert plan["runner_kind"] == "deterministic_local"
    assert plan["missing_inputs"] == ["root", "workspace_id"]
    assert plan["scenario"] is None


def test_runner_discovers_workspace_changed_files_and_release_from_default_catalog():
    runner = _runner()

    assert "workspace.changed_files" in _ids(runner.list_capabilities())
    assert "workspace.release" in _ids(
        runner.search_capabilities(query="workspace release")["capabilities"]
    )

    changed_description = runner.describe_capability("workspace.changed_files")
    release_description = runner.describe_capability("workspace.release")
    assert changed_description["input_contract"]["required"] == [
        "root",
        "cwd",
        "workspace_id",
    ]
    assert release_description["input_contract"]["required"] == ["root", "workspace_id"]
    assert "diff_summary_only" in changed_description["safety_boundaries"]
    assert "deletes_only_materialized_workspace" in release_description["safety_boundaries"]


def test_runner_reports_workspace_changed_files_against_source(tmp_path):
    source = tmp_path / "repo"
    (source / "src").mkdir(parents=True)
    (source / "src" / "app.py").write_text("old\n", encoding="utf-8")
    (source / "src" / "delete.py").write_text("delete me\n", encoding="utf-8")
    (source / "README.md").write_text("same\n", encoding="utf-8")
    root = tmp_path / "state"
    workspace_root = root / "workspaces" / "workspace_native_coding_slice_9"
    (workspace_root / "src").mkdir(parents=True)
    (workspace_root / "src" / "app.py").write_text("new\n", encoding="utf-8")
    (workspace_root / "src" / "new.py").write_text("added\n", encoding="utf-8")
    (workspace_root / "README.md").write_text("same\n", encoding="utf-8")

    result = _runner().run_capability(
        "workspace.changed_files",
        inputs={
            "root": str(root),
            "cwd": str(source),
            "workspace_id": "workspace_native_coding_slice_9",
            "include_paths": ["src", "README.md"],
        },
    )

    changed = result["changed_files"]
    assert result["kind"] == "capability_run_result"
    assert result["capability_id"] == "workspace.changed_files"
    assert result["status"] == "completed"
    assert result["runner_kind"] == "deterministic_readonly"
    assert changed["status"] == "changed"
    assert changed["workspace_id"] == "workspace_native_coding_slice_9"
    assert changed["changed_file_count"] == 3
    assert changed["changed_files"] == [
        {"path": "src/app.py", "status": "modified"},
        {"path": "src/delete.py", "status": "deleted"},
        {"path": "src/new.py", "status": "added"},
    ]
    assert changed["artifact_write"] == "not_performed"
    assert changed["content_policy"] == "diff_summary_only"


def test_workspace_changed_files_rejects_missing_materialized_workspace(tmp_path):
    source = tmp_path / "repo"
    source.mkdir()

    with pytest.raises(ValueError, match="materialized workspace"):
        _runner().run_capability(
            "workspace.changed_files",
            inputs={
                "root": str(tmp_path / "state"),
                "cwd": str(source),
                "workspace_id": "workspace_missing",
            },
        )


def test_runner_releases_materialized_workspace_without_touching_source(tmp_path):
    source = tmp_path / "repo"
    source.mkdir()
    (source / "keep.py").write_text("source\n", encoding="utf-8")
    root = tmp_path / "state"
    workspace_root = root / "workspaces" / "workspace_native_coding_slice_9"
    workspace_root.mkdir(parents=True)
    (workspace_root / "temp.py").write_text("generated\n", encoding="utf-8")

    result = _runner().run_capability(
        "workspace.release",
        inputs={
            "root": str(root),
            "workspace_id": "workspace_native_coding_slice_9",
        },
    )

    released = result["released_workspace"]
    assert result["kind"] == "capability_run_result"
    assert result["capability_id"] == "workspace.release"
    assert result["status"] == "completed"
    assert result["runner_kind"] == "deterministic_local"
    assert released["status"] == "released"
    assert released["workspace_id"] == "workspace_native_coding_slice_9"
    assert released["removed_path"] == str(workspace_root)
    assert released["event_append"] == "not_performed"
    assert not workspace_root.exists()
    assert (source / "keep.py").read_text(encoding="utf-8") == "source\n"


def test_workspace_release_rejects_unknown_workspace_without_side_effects(tmp_path):
    root = tmp_path / "state"
    root.mkdir()

    with pytest.raises(ValueError, match="materialized workspace"):
        _runner().run_capability(
            "workspace.release",
            inputs={
                "root": str(root),
                "workspace_id": "workspace_missing",
            },
        )

    assert root.exists()


def test_workspace_changed_files_plan_stops_when_required_inputs_are_missing():
    plan = _runner().plan_capability_run(
        "workspace.changed_files",
        inputs={"cwd": "/tmp/project"},
    )

    assert plan["can_launch"] is False
    assert plan["status"] == "missing_inputs"
    assert plan["runner_kind"] == "deterministic_readonly"
    assert plan["missing_inputs"] == ["root", "workspace_id"]
    assert plan["scenario"] is None


def test_runner_discovers_artifact_diff_summary_and_changed_files_from_default_catalog():
    runner = _runner()

    assert "artifact.diff_summary" in _ids(runner.list_capabilities())
    assert "artifact.changed_files" in _ids(
        runner.search_capabilities(query="artifact changed files")["capabilities"]
    )

    diff_description = runner.describe_capability("artifact.diff_summary")
    changed_description = runner.describe_capability("artifact.changed_files")
    required = ["root", "cwd", "workspace_id", "run_id", "execution_id"]
    assert diff_description["input_contract"]["required"] == required
    assert changed_description["input_contract"]["required"] == required
    assert "writes_only_artifact_store" in diff_description["safety_boundaries"]
    assert "no_event_append" in changed_description["safety_boundaries"]


def test_runner_writes_changed_files_artifact_from_materialized_workspace(tmp_path):
    source = tmp_path / "repo"
    (source / "src").mkdir(parents=True)
    (source / "src" / "app.py").write_text("old secret\n", encoding="utf-8")
    root = tmp_path / "state"
    workspace_root = root / "workspaces" / "workspace_native_coding_slice_10"
    (workspace_root / "src").mkdir(parents=True)
    (workspace_root / "src" / "app.py").write_text("new secret\n", encoding="utf-8")
    (workspace_root / "src" / "new.py").write_text("added secret\n", encoding="utf-8")

    result = _runner().run_capability(
        "artifact.changed_files",
        inputs={
            "root": str(root),
            "cwd": str(source),
            "workspace_id": "workspace_native_coding_slice_10",
            "run_id": "run_native_coding",
            "execution_id": "execution_changed_files",
            "include_paths": ["src"],
        },
    )

    artifact = result["artifact"]
    content = json.loads(ArtifactStore(root).get_content(artifact["artifact_id"]))
    assert result["kind"] == "capability_run_result"
    assert result["capability_id"] == "artifact.changed_files"
    assert result["status"] == "completed"
    assert result["runner_kind"] == "deterministic_local"
    assert artifact["artifact_type"] == "native_coding.changed_files"
    assert artifact["ref"] == {
        "ref_type": "artifact",
        "scope": "run",
        "run_id": "run_native_coding",
        "artifact_id": artifact["artifact_id"],
    }
    assert artifact["artifact_write"] == "performed"
    assert artifact["event_append"] == "not_performed"
    assert content["changed_file_count"] == 2
    assert content["changed_files"] == [
        {"path": "src/app.py", "status": "modified"},
        {"path": "src/new.py", "status": "added"},
    ]
    assert "secret" not in json.dumps(content)


def test_runner_writes_diff_summary_artifact_without_raw_file_content(tmp_path):
    source = tmp_path / "repo"
    (source / "src").mkdir(parents=True)
    (source / "src" / "app.py").write_text("old raw content\n", encoding="utf-8")
    root = tmp_path / "state"
    workspace_root = root / "workspaces" / "workspace_native_coding_slice_10"
    (workspace_root / "src").mkdir(parents=True)
    (workspace_root / "src" / "app.py").write_text("new raw content\n", encoding="utf-8")

    result = _runner().run_capability(
        "artifact.diff_summary",
        inputs={
            "root": str(root),
            "cwd": str(source),
            "workspace_id": "workspace_native_coding_slice_10",
            "run_id": "run_native_coding",
            "execution_id": "execution_diff_summary",
            "include_paths": ["src"],
        },
    )

    artifact = result["artifact"]
    metadata = ArtifactStore(root).get_metadata(artifact["artifact_id"])
    content_text = ArtifactStore(root).get_content(artifact["artifact_id"])
    content = json.loads(content_text)
    assert artifact["artifact_type"] == "native_coding.diff_summary"
    assert metadata["summary"] == "1 changed file in workspace_native_coding_slice_10"
    assert content["summary_lines"] == ["modified src/app.py"]
    assert content["content_policy"] == "diff_summary_only"
    assert "old raw content" not in content_text
    assert "new raw content" not in content_text


def test_artifact_changed_files_plan_stops_when_required_inputs_are_missing():
    plan = _runner().plan_capability_run(
        "artifact.changed_files",
        inputs={"cwd": "/tmp/project", "run_id": "run_native_coding"},
    )

    assert plan["can_launch"] is False
    assert plan["status"] == "missing_inputs"
    assert plan["runner_kind"] == "deterministic_local"
    assert plan["missing_inputs"] == ["root", "workspace_id", "execution_id"]
    assert plan["scenario"] is None


def test_runner_discovers_code_read_and_search_from_default_catalog():
    runner = _runner()

    assert "code.read" in _ids(runner.list_capabilities())
    assert "code.search" in _ids(runner.search_capabilities(query="code search")["capabilities"])

    read_description = runner.describe_capability("code.read")
    search_description = runner.describe_capability("code.search")
    assert read_description["input_contract"]["required"] == ["root", "cwd", "path"]
    assert search_description["input_contract"]["required"] == ["root", "cwd", "query"]
    assert "relative_paths_only" in read_description["safety_boundaries"]
    assert "limited_excerpts_only" in read_description["safety_boundaries"]
    assert "no_filesystem_write" in search_description["safety_boundaries"]


def test_coding_related_capabilities_mark_routing_inputs_as_system_only():
    runner = _runner()

    for capability_id in (
        "code.search",
        "code.read",
        "code.apply_patch",
        "test.run",
        "coding_task.execute",
    ):
        description = runner.describe_capability(capability_id)
        properties = description["input_contract"]["properties"]
        assert properties["root"]["x-system-input"] is True
        assert properties["cwd"]["x-system-input"] is True
    execute_properties = runner.describe_capability("coding_task.execute")[
        "input_contract"
    ]["properties"]
    for name in ("workspace_id", "run_id", "execution_id"):
        assert execute_properties[name]["x-system-input"] is True


def test_runner_reads_code_file_excerpt_without_side_effects(tmp_path):
    workspace = tmp_path / "repo"
    source_dir = workspace / "src"
    source_dir.mkdir(parents=True)
    source = source_dir / "app.py"
    source.write_text(
        "def alpha():\n"
        "    return 'needle one'\n"
        "\n"
        "def beta():\n"
        "    return 'needle two'\n",
        encoding="utf-8",
    )
    root = tmp_path / "state"

    result = _runner().run_capability(
        "code.read",
        inputs={
            "root": str(root),
            "cwd": str(workspace),
            "path": "src/app.py",
            "max_excerpt_chars": 37,
        },
    )

    code_read = result["code_read"]
    assert result["kind"] == "capability_run_result"
    assert result["capability_id"] == "code.read"
    assert result["status"] == "completed"
    assert result["runner_kind"] == "deterministic_readonly"
    assert code_read["status"] == "readable"
    assert code_read["path"] == "src/app.py"
    assert code_read["line_count"] == 5
    assert code_read["excerpt"] == "def alpha():\n    return 'needle one'\n"
    assert code_read["truncated"] is True
    assert code_read["code_ref"]["ref_type"] == "code"
    assert code_read["code_ref"]["scope"] == "workspace"
    assert code_read["code_ref"]["path"] == "src/app.py"
    assert len(code_read["code_ref"]["sha256"]) == 64
    assert "content" not in code_read
    assert not list(root.rglob("*"))


def test_runner_searches_code_with_limited_line_excerpts(tmp_path):
    workspace = tmp_path / "repo"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "app.py").write_text(
        "def alpha():\n    return 'needle one'\n",
        encoding="utf-8",
    )
    (workspace / "src" / "other.py").write_text(
        "needle two\nneedle three\n",
        encoding="utf-8",
    )
    root = tmp_path / "state"

    result = _runner().run_capability(
        "code.search",
        inputs={
            "root": str(root),
            "cwd": str(workspace),
            "query": "needle",
            "include_paths": ["src"],
            "max_results": 2,
            "max_excerpt_chars": 18,
        },
    )

    code_search = result["code_search"]
    assert result["capability_id"] == "code.search"
    assert result["runner_kind"] == "deterministic_readonly"
    assert code_search["status"] == "matched"
    assert code_search["query"] == "needle"
    assert code_search["match_count"] == 2
    assert code_search["truncated"] is True
    assert code_search["matches"] == [
        {
            "path": "src/app.py",
            "line_number": 2,
            "excerpt": "    return 'needle",
            "truncated": True,
            "code_ref": {
                "ref_type": "code",
                "scope": "workspace",
                "path": "src/app.py",
                "line_number": 2,
            },
        },
        {
            "path": "src/other.py",
            "line_number": 1,
            "excerpt": "needle two",
            "truncated": False,
            "code_ref": {
                "ref_type": "code",
                "scope": "workspace",
                "path": "src/other.py",
                "line_number": 1,
            },
        },
    ]
    assert not list(root.rglob("*"))


@pytest.mark.parametrize(
    ("capability_id", "inputs", "message"),
    [
        ("code.read", {"path": "../secret.py"}, "path"),
        ("code.read", {"path": "/tmp/secret.py"}, "path"),
        ("code.search", {"include_paths": ["../src"]}, "include_paths"),
        ("code.search", {"include_paths": ["/tmp/src"]}, "include_paths"),
    ],
)
def test_code_capabilities_reject_paths_outside_workspace(
    tmp_path, capability_id, inputs, message
):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    payload = {
        "root": str(tmp_path / "state"),
        "cwd": str(workspace),
        "path": "src/app.py",
        "query": "needle",
    }
    payload.update(inputs)

    with pytest.raises(ValueError, match=message):
        _runner().run_capability(capability_id, inputs=payload)


def test_code_read_plan_stops_when_required_inputs_are_missing():
    plan = _runner().plan_capability_run(
        "code.read",
        inputs={"cwd": "/tmp/project"},
    )

    assert plan["can_launch"] is False
    assert plan["status"] == "missing_inputs"
    assert plan["runner_kind"] == "deterministic_readonly"
    assert plan["missing_inputs"] == ["root", "path"]
    assert plan["scenario"] is None


def test_runner_discovers_code_apply_patch_from_default_catalog():
    runner = _runner()

    assert "code.apply_patch" in _ids(runner.list_capabilities())
    search = runner.search_capabilities(query="apply patch")

    assert "code.apply_patch" in _ids(search["capabilities"])
    description = runner.describe_capability("code.apply_patch")
    assert description["input_contract"]["required"] == ["root", "cwd", "patch"]
    assert "unified_diff_only" in description["safety_boundaries"]
    assert "workspace_escape_rejected" in description["safety_boundaries"]


def test_runner_applies_unified_patch_inside_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    target = workspace / "src" / "app.py"
    target.write_text(
        "def alpha():\n"
        "    return 'old'\n",
        encoding="utf-8",
    )
    patch = (
        "--- a/src/app.py\n"
        "+++ b/src/app.py\n"
        "@@ -1,2 +1,3 @@\n"
        " def alpha():\n"
        "-    return 'old'\n"
        "+    value = 'new'\n"
        "+    return value\n"
    )
    root = tmp_path / "state"

    result = _runner().run_capability(
        "code.apply_patch",
        inputs={
            "root": str(root),
            "cwd": str(workspace),
            "patch": patch,
        },
    )

    patch_result = result["patch_result"]
    assert result["kind"] == "capability_run_result"
    assert result["capability_id"] == "code.apply_patch"
    assert result["status"] == "completed"
    assert result["runner_kind"] == "deterministic_local"
    assert patch_result["status"] == "applied"
    assert patch_result["changed_files"] == ["src/app.py"]
    assert patch_result["file_count"] == 1
    assert patch_result["hunk_count"] == 1
    assert patch_result["write_policy"] == "workspace_relative_patch_only"
    assert target.read_text(encoding="utf-8") == (
        "def alpha():\n"
        "    value = 'new'\n"
        "    return value\n"
    )
    assert not list(root.rglob("*"))


def test_code_apply_patch_rejects_path_escape_without_writing(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("keep\n", encoding="utf-8")
    patch = (
        "--- a/../outside.py\n"
        "+++ b/../outside.py\n"
        "@@ -1 +1 @@\n"
        "-keep\n"
        "+changed\n"
    )

    with pytest.raises(ValueError, match="patch path"):
        _runner().run_capability(
            "code.apply_patch",
            inputs={
                "root": str(tmp_path / "state"),
                "cwd": str(workspace),
                "patch": patch,
            },
        )

    assert outside.read_text(encoding="utf-8") == "keep\n"


def test_code_apply_patch_rejects_context_mismatch_without_partial_write(tmp_path):
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    target = workspace / "src" / "app.py"
    target.write_text("actual\n", encoding="utf-8")
    patch = (
        "--- a/src/app.py\n"
        "+++ b/src/app.py\n"
        "@@ -1 +1 @@\n"
        "-expected\n"
        "+changed\n"
    )

    with pytest.raises(ValueError, match="patch context mismatch"):
        _runner().run_capability(
            "code.apply_patch",
            inputs={
                "root": str(tmp_path / "state"),
                "cwd": str(workspace),
                "patch": patch,
            },
        )

    assert target.read_text(encoding="utf-8") == "actual\n"


def test_code_apply_patch_plan_stops_when_required_inputs_are_missing():
    plan = _runner().plan_capability_run(
        "code.apply_patch",
        inputs={"cwd": "/tmp/project"},
    )

    assert plan["can_launch"] is False
    assert plan["status"] == "missing_inputs"
    assert plan["runner_kind"] == "deterministic_local"
    assert plan["missing_inputs"] == ["root", "patch"]
    assert plan["scenario"] is None


def test_runner_discovers_test_run_from_default_catalog():
    runner = _runner()

    assert "test.run" in _ids(runner.list_capabilities())
    search = runner.search_capabilities(query="test run")

    assert "test.run" in _ids(search["capabilities"])
    description = runner.describe_capability("test.run")
    assert description["input_contract"]["required"] == ["root", "cwd", "argv"]
    assert description["input_contract"]["properties"]["argv"]["type"] == "array"
    assert "argv_allowlist_only" in description["safety_boundaries"]
    assert "shell_false" in description["safety_boundaries"]


def test_runner_runs_allowlisted_test_command_without_artifact_write(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    root = tmp_path / "state"

    result = _runner().run_capability(
        "test.run",
        inputs={
            "root": str(root),
            "cwd": str(workspace),
            "argv": ["printf", "ok\n"],
        },
    )

    test_result = result["test_result"]
    assert result["kind"] == "capability_run_result"
    assert result["capability_id"] == "test.run"
    assert result["status"] == "completed"
    assert result["runner_kind"] == "deterministic_local"
    assert test_result["status"] == "passed"
    assert test_result["exit_code"] == 0
    assert test_result["argv"] == ["printf", "ok\n"]
    assert test_result["stdout_excerpt"] == "ok\n"
    assert test_result["stderr_excerpt"] == ""
    assert test_result["output_truncated"] is False
    assert test_result["artifact_write"] == "not_performed"
    assert not list(root.rglob("*"))


def test_test_run_reports_nonzero_exit_without_raising(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    result = _runner().run_capability(
        "test.run",
        inputs={
            "root": str(tmp_path / "state"),
            "cwd": str(workspace),
            "argv": ["false"],
        },
    )

    assert result["test_result"]["status"] == "failed"
    assert result["test_result"]["exit_code"] == 1
    assert result["test_result"]["reason_code"] == "terminal_exit_nonzero"


def test_test_run_rejects_not_allowlisted_command_without_side_effects(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    root = tmp_path / "state"

    with pytest.raises(PermissionError, match="terminal command is not allowed"):
        _runner().run_capability(
            "test.run",
            inputs={
                "root": str(root),
                "cwd": str(workspace),
                "argv": ["python3", "-c", "print('not allowlisted')"],
            },
        )

    assert not list(root.rglob("*"))


def test_test_run_plan_stops_when_required_inputs_are_missing():
    plan = _runner().plan_capability_run(
        "test.run",
        inputs={"cwd": "/tmp/project"},
    )

    assert plan["can_launch"] is False
    assert plan["status"] == "missing_inputs"
    assert plan["runner_kind"] == "deterministic_local"
    assert plan["missing_inputs"] == ["root", "argv"]
    assert plan["scenario"] is None


def test_runner_discovers_vcs_status_and_diff_from_default_catalog():
    runner = _runner()

    assert "vcs.status" in _ids(runner.list_capabilities())
    assert "vcs.diff" in _ids(runner.search_capabilities(query="vcs diff")["capabilities"])

    status_description = runner.describe_capability("vcs.status")
    diff_description = runner.describe_capability("vcs.diff")
    assert status_description["input_contract"]["required"] == ["root", "cwd"]
    assert diff_description["input_contract"]["required"] == ["root", "cwd"]
    assert "fixed_git_subcommands_only" in status_description["safety_boundaries"]
    assert "diff_summary_only" in diff_description["safety_boundaries"]


def test_runner_reports_git_status_summary_without_artifact_write(tmp_path):
    repo = _git_repo(tmp_path)
    (repo / "app.py").write_text("print('new')\n", encoding="utf-8")
    (repo / "new.py").write_text("print('new file')\n", encoding="utf-8")
    root = tmp_path / "state"

    result = _runner().run_capability(
        "vcs.status",
        inputs={
            "root": str(root),
            "cwd": str(repo),
        },
    )

    status = result["vcs_status"]
    assert result["kind"] == "capability_run_result"
    assert result["capability_id"] == "vcs.status"
    assert result["status"] == "completed"
    assert result["runner_kind"] == "deterministic_readonly"
    assert status["status"] == "dirty"
    assert status["branch"] in {"master", "main"}
    assert status["changed_files"] == [
        {"path": "app.py", "index_status": " ", "worktree_status": "M"},
        {"path": "new.py", "index_status": "?", "worktree_status": "?"},
    ]
    assert status["changed_file_count"] == 2
    assert status["artifact_write"] == "not_performed"
    assert not list(root.rglob("*"))


def test_runner_reports_git_diff_summary_and_changed_files(tmp_path):
    repo = _git_repo(tmp_path)
    (repo / "app.py").write_text("print('new')\n", encoding="utf-8")
    root = tmp_path / "state"

    result = _runner().run_capability(
        "vcs.diff",
        inputs={
            "root": str(root),
            "cwd": str(repo),
        },
    )

    diff = result["vcs_diff"]
    assert result["capability_id"] == "vcs.diff"
    assert result["runner_kind"] == "deterministic_readonly"
    assert diff["status"] == "changed"
    assert diff["changed_files"] == ["app.py"]
    assert diff["changed_file_count"] == 1
    assert "app.py" in diff["stat_excerpt"]
    assert "print('new')" not in repr(diff)
    assert diff["artifact_write"] == "not_performed"
    assert not list(root.rglob("*"))


def test_vcs_capabilities_reject_non_git_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with pytest.raises(ValueError, match="git repository"):
        _runner().run_capability(
            "vcs.status",
            inputs={
                "root": str(tmp_path / "state"),
                "cwd": str(workspace),
            },
        )


def test_vcs_status_plan_stops_when_required_inputs_are_missing():
    plan = _runner().plan_capability_run(
        "vcs.status",
        inputs={"cwd": "/tmp/project"},
    )

    assert plan["can_launch"] is False
    assert plan["status"] == "missing_inputs"
    assert plan["runner_kind"] == "deterministic_readonly"
    assert plan["missing_inputs"] == ["root"]
    assert plan["scenario"] is None


def test_runner_status_mirrors_catalog_status_without_executing_capability():
    catalog = CapabilityCatalog(
        capabilities=[
            _capability(
                "llm.artifact.review",
                "product_candidate",
                required_env=("ISOTOPE_TEST_PROVIDER_KEY",),
                network_required=True,
                provider="test-provider",
                model="test-model",
            )
        ]
    )

    status = _runner(catalog=catalog).get_capability_status(
        "llm.artifact.review", env={}
    )

    assert status["capability_id"] == "llm.artifact.review"
    assert status["status"] == "missing_configuration"
    assert status["ready"] is False
    assert status["missing_env"] == ["ISOTOPE_TEST_PROVIDER_KEY"]


@pytest.mark.parametrize(
    ("capability_id", "scenario"),
    [
        ("artifact.review", "artifact-review"),
        ("external.snapshot.review", "external-snapshot-review"),
        ("approval.tool.runner", "approval-tool-runner"),
    ],
)
def test_runner_can_run_allowlisted_product_candidate_capability(
    tmp_path, capability_id, scenario
):
    result = _runner().run_capability(capability_id, root_path=tmp_path)

    assert result["capability_id"] == capability_id
    assert result["status"] == "completed"
    assert result["scenario"] == scenario
    assert result["replay_ok"] is True
    assert result["checkpoint_ok"] is True
    json.dumps(result)
    for mapping in _walk_mapping(result):
        assert FORBIDDEN_RESULT_KEYS.isdisjoint(mapping)


def test_unknown_capability_fails_closed_before_side_effects(tmp_path):
    with pytest.raises(ValueError, match="unknown capability"):
        _runner().run_capability("unknown.capability", root_path=tmp_path)

    assert not list(Path(tmp_path).rglob("*"))


@pytest.mark.parametrize("shelf", ["diagnostic", "experimental"])
def test_diagnostic_and_experimental_capabilities_do_not_run_by_default(tmp_path, shelf):
    catalog = CapabilityCatalog(
        capabilities=[_capability(f"{shelf}.capability", shelf)]
    )

    with pytest.raises(PermissionError, match=shelf):
        _runner(catalog=catalog).run_capability(
            f"{shelf}.capability", root_path=tmp_path
        )

    assert not list(Path(tmp_path).rglob("*"))


def test_provider_required_capability_fails_closed_without_constructing_provider(tmp_path):
    catalog = CapabilityCatalog(
        capabilities=[
            _capability(
                "llm.artifact.review",
                "product_candidate",
                required_env=("ISOTOPE_TEST_PROVIDER_KEY",),
                network_required=True,
                provider="deepseek",
                model="deepseek-v4-flash",
            )
        ]
    )

    with pytest.raises(PermissionError, match="missing_configuration"):
        _runner(catalog=catalog).run_capability(
            "llm.artifact.review", root_path=tmp_path, env={}
        )

    assert not list(Path(tmp_path).rglob("*"))


def test_unallowlisted_ready_capability_fails_closed_before_side_effects(tmp_path):
    catalog = CapabilityCatalog(
        capabilities=[_capability("custom.ready.capability", "product_candidate")]
    )

    with pytest.raises(PermissionError, match="not allowlisted"):
        _runner(catalog=catalog).run_capability(
            "custom.ready.capability", root_path=tmp_path
        )

    assert not list(Path(tmp_path).rglob("*"))


def test_runner_plan_rejects_malformed_inputs_mapping():
    with pytest.raises(ValueError, match="inputs"):
        _runner().plan_capability_run("artifact.review", inputs=[])


def test_runner_run_rejects_malformed_inputs_mapping_without_side_effects(tmp_path):
    with pytest.raises(ValueError, match="inputs"):
        _runner().run_capability(
            "artifact.review",
            root_path=tmp_path,
            inputs=[],
        )

    assert not list(Path(tmp_path).rglob("*"))


def test_request_context_plan_stops_when_required_inputs_are_missing():
    plan = _runner().plan_capability_run(
        "supervisor.request_context",
        inputs={"cwd": "/tmp/project"},
    )

    assert plan["can_launch"] is False
    assert plan["status"] == "missing_inputs"
    assert plan["runner_kind"] == "deterministic_readonly"
    assert plan["missing_inputs"] == ["state_root", "query"]
    assert plan["scenario"] is None


def test_worker_review_plan_stops_when_required_inputs_are_missing():
    plan = _runner().plan_capability_run("supervisor.worker_review", inputs={})

    assert plan["can_launch"] is False
    assert plan["status"] == "missing_inputs"
    assert plan["runner_kind"] == "deterministic_readonly"
    assert plan["missing_inputs"] == ["state_root"]
    assert plan["scenario"] is None


def test_integration_review_plan_stops_when_required_inputs_are_missing():
    plan = _runner().plan_capability_run("supervisor.integration_review", inputs={})

    assert plan["can_launch"] is False
    assert plan["status"] == "missing_inputs"
    assert plan["runner_kind"] == "deterministic_readonly"
    assert plan["missing_inputs"] == ["state_root"]
    assert plan["scenario"] is None


def test_memory_query_plan_stops_when_required_inputs_are_missing():
    plan = _runner().plan_capability_run(
        "memory.query",
        inputs={"root": "/tmp/isotope-runtime", "query": "memory boundary"},
    )

    assert plan["can_launch"] is False
    assert plan["status"] == "missing_inputs"
    assert plan["runner_kind"] == "deterministic_readonly"
    assert plan["missing_inputs"] == ["run_id"]
    assert plan["scenario"] is None


def test_memory_promotion_preview_plan_stops_when_required_inputs_are_missing():
    plan = _runner().plan_capability_run(
        "memory.promotion.preview",
        inputs={
            "run_id": "run_memory",
            "agent_id": "agent_memo",
            "thread_id": "thread_memory",
        },
    )

    assert plan["can_launch"] is False
    assert plan["status"] == "missing_inputs"
    assert plan["runner_kind"] == "deterministic_readonly"
    assert plan["missing_inputs"] == ["candidate"]
    assert plan["scenario"] is None


def test_screen_report_plan_stops_when_required_inputs_are_missing():
    plan = _runner().plan_capability_run(
        "screen.report",
        inputs={"root": "/tmp/isotope-runtime"},
    )

    assert plan["can_launch"] is False
    assert plan["status"] == "missing_inputs"
    assert plan["runner_kind"] == "deterministic_readonly"
    assert plan["missing_inputs"] == ["run_id"]
    assert plan["scenario"] is None


def test_screen_observe_plan_stops_when_target_selector_is_missing(tmp_path):
    plan = _runner().plan_capability_run(
        "screen.observe",
        inputs={"root": str(tmp_path)},
    )

    assert plan["can_launch"] is False
    assert plan["status"] == "missing_inputs"
    assert plan["runner_kind"] == "deterministic_local"
    assert plan["missing_inputs"] == ["target_selector"]
    assert plan["scenario"] is None


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("root", 123),
        ("query", {"text": "memory"}),
        ("run_id", ["run_001"]),
        ("scope", "project"),
        ("limit", 0),
        ("controlled_expand", "yes"),
        ("expand_budget", True),
    ],
)
def test_memory_query_plan_rejects_invalid_inputs(field_name, bad_value):
    inputs = {
        "root": "/tmp/isotope-runtime",
        "query": "memory boundary",
        "run_id": "run_001",
    }
    inputs[field_name] = bad_value

    with pytest.raises(ValueError, match=field_name):
        _runner().plan_capability_run("memory.query", inputs=inputs)


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("run_id", 123),
        ("agent_id", {"agent": "memo"}),
        ("thread_id", ["thread_memory"]),
        ("candidate", "raw text"),
        ("scope", "project"),
        ("quality", ""),
    ],
)
def test_memory_promotion_preview_plan_rejects_invalid_inputs(field_name, bad_value):
    inputs = {
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
            "summary": "Memory promotion preview.",
            "provenance": {"execution_id": "exec_report"},
        },
    }
    inputs[field_name] = bad_value

    with pytest.raises((TypeError, ValueError), match=field_name):
        _runner().plan_capability_run("memory.promotion.preview", inputs=inputs)


def test_research_search_plan_is_launchable_with_runtime_provider_policy():
    plan = _runner().plan_capability_run(
        "research.search",
        inputs={
            "root": "/tmp/isotope-runtime",
            "query": "capacity research integration",
        },
    )

    assert plan["can_launch"] is True
    assert plan["status"] == "launchable"
    assert plan["missing_inputs"] == []


def test_worker_review_plan_rejects_non_string_state_root():
    with pytest.raises(ValueError, match="state_root"):
        _runner().plan_capability_run(
            "supervisor.worker_review",
            inputs={"state_root": 123},
        )


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("state_root", 123),
        ("base_ref", ["main"]),
    ],
)
def test_integration_review_plan_rejects_non_string_inputs(field_name, bad_value):
    inputs = {"state_root": "/tmp/supervisor-state", "base_ref": "main"}
    inputs[field_name] = bad_value

    with pytest.raises(ValueError, match=field_name):
        _runner().plan_capability_run("supervisor.integration_review", inputs=inputs)


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("include_unfinished", "false"),
        ("include_missing_worktrees", 1),
        ("run_test_gate", "false"),
        ("run_candidate_validation", None),
    ],
)
def test_integration_review_plan_rejects_non_boolean_flags(field_name, bad_value):
    inputs = {"codex_home": "/tmp/codex-home", field_name: bad_value}

    with pytest.raises(ValueError, match=field_name):
        _runner().plan_capability_run("supervisor.integration_review", inputs=inputs)


def test_integration_review_plan_rejects_inputs_outside_contract():
    with pytest.raises(ValueError, match="not allowed by input_contract"):
        _runner().plan_capability_run(
            "supervisor.integration_review",
            inputs={
                "codex_home": "/tmp/codex-home",
                "prompt": "PRIVATE_CONTENT_SHOULD_NOT_PASS",
            },
        )


def test_worker_review_plan_rejects_inputs_outside_contract():
    with pytest.raises(ValueError, match="not allowed by input_contract"):
        _runner().plan_capability_run(
            "supervisor.worker_review",
            inputs={
                "codex_home": "/tmp/codex-home",
                "prompt": "PRIVATE_CONTENT_SHOULD_NOT_PASS",
            },
        )


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("state_root", 123),
        ("cwd", ["workspace"]),
        ("query", {"text": "request_context"}),
    ],
)
def test_request_context_plan_rejects_non_string_required_inputs(field_name, bad_value):
    inputs = {
        "state_root": "/tmp/supervisor-state",
        "cwd": "/tmp/workspace",
        "query": "request_context",
    }
    inputs[field_name] = bad_value

    with pytest.raises(ValueError, match=field_name):
        _runner().plan_capability_run("supervisor.request_context", inputs=inputs)


@pytest.mark.parametrize("bad_max_results", [0, -1, "3", True])
def test_request_context_plan_rejects_invalid_max_results(bad_max_results):
    with pytest.raises(ValueError, match="max_results"):
        _runner().plan_capability_run(
            "supervisor.request_context",
            inputs={
                "codex_home": "/tmp/codex-home",
                "cwd": "/tmp/workspace",
                "query": "request_context",
                "max_results": bad_max_results,
            },
        )


def test_request_context_plan_rejects_inputs_outside_contract():
    with pytest.raises(ValueError, match="not allowed by input_contract"):
        _runner().plan_capability_run(
            "supervisor.request_context",
            inputs={
                "codex_home": "/tmp/codex-home",
                "cwd": "/tmp/workspace",
                "query": "request_context",
                "raw_content": "PRIVATE_CONTENT_SHOULD_NOT_PASS",
            },
        )


def test_request_context_run_rejects_non_string_query_without_coercion(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with pytest.raises(ValueError, match="query"):
        _runner().run_capability(
            "supervisor.request_context",
            inputs={
                "codex_home": str(tmp_path / "codex-home"),
                "cwd": str(workspace),
                "query": 123,
                "max_results": 1,
            },
        )

    assert not (tmp_path / "codex-home" / "supervisor" / "context_results.jsonl").exists()


def test_request_context_run_rejects_inputs_outside_contract_without_side_effects(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with pytest.raises(ValueError, match="not allowed by input_contract"):
        _runner().run_capability(
            "supervisor.request_context",
            inputs={
                "codex_home": str(tmp_path / "codex-home"),
                "cwd": str(workspace),
                "query": "request_context",
                "max_results": 1,
                "raw_content": "PRIVATE_CONTENT_SHOULD_NOT_PASS",
            },
        )

    assert not (tmp_path / "codex-home" / "supervisor" / "context_results.jsonl").exists()


def test_runner_plan_rejects_input_with_wrong_contract_type():
    catalog = CapabilityCatalog(
        capabilities=[
            _capability(
                "custom.typed.capability",
                "product_candidate",
                input_contract={
                    "type": "object",
                    "required": [],
                    "properties": {"max_results": {"type": "integer"}},
                },
            )
        ]
    )

    with pytest.raises(ValueError, match="does not match input_contract type"):
        _runner(catalog=catalog).plan_capability_run(
            "custom.typed.capability",
            inputs={"max_results": "5"},
        )


def test_runner_plan_rejects_input_outside_contract_enum():
    catalog = CapabilityCatalog(
        capabilities=[
            _capability(
                "custom.mode.capability",
                "product_candidate",
                input_contract={
                    "type": "object",
                    "required": [],
                    "properties": {
                        "mode": {"type": "string", "enum": ["summary", "detail"]}
                    },
                },
            )
        ]
    )

    with pytest.raises(ValueError, match="not allowed by input_contract enum"):
        _runner(catalog=catalog).plan_capability_run(
            "custom.mode.capability",
            inputs={"mode": "raw"},
        )


def test_runner_run_rejects_input_with_wrong_contract_type_before_allowlist(tmp_path):
    catalog = CapabilityCatalog(
        capabilities=[
            _capability(
                "custom.typed.capability",
                "product_candidate",
                input_contract={
                    "type": "object",
                    "required": [],
                    "properties": {"max_results": {"type": "integer"}},
                },
            )
        ]
    )

    with pytest.raises(ValueError, match="does not match input_contract type"):
        _runner(catalog=catalog).run_capability(
            "custom.typed.capability",
            root_path=tmp_path,
            inputs={"max_results": "5"},
        )

    assert not list(Path(tmp_path).rglob("*"))


def test_request_context_capability_runs_existing_readonly_context_search(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "README.md").write_text(
        "# Project\n\nSupervisor request_context finds capability evidence.\n",
        encoding="utf-8",
    )
    codex_home = tmp_path / "codex-home"

    result = _runner().run_capability(
        "supervisor.request_context",
        inputs={
            "codex_home": str(codex_home),
            "cwd": str(workspace),
            "query": "request_context capability evidence",
            "max_results": 3,
        },
    )

    assert result["kind"] == "capability_run_result"
    assert result["capability_id"] == "supervisor.request_context"
    assert result["status"] == "completed"
    assert result["runner_kind"] == "deterministic_readonly"
    assert result["context_result"]["backend"] == "bm25"
    assert result["context_result"]["query"] == "request_context capability evidence"
    assert isinstance(result["context_result"]["created_at"], str)
    assert result["context_result"]["created_at"]
    assert result["context_result"]["item_count"] >= 1
    assert (codex_home / "supervisor" / "context_results.jsonl").is_file()
    json.dumps(result)
    for mapping in _walk_mapping(result):
        assert FORBIDDEN_RESULT_KEYS.isdisjoint(mapping)


def test_worker_review_capability_runs_existing_lightweight_review(tmp_path):
    codex_home = tmp_path / "codex-home"
    workspace = tmp_path / "repo" / ".worktrees" / "supervisor" / "feature-a"
    workspace.mkdir(parents=True)
    log_path = codex_home / "supervisor" / "logs" / "managed-001.log"
    log_path.parent.mkdir(parents=True)
    log_path.write_text(
        "\n".join(
            [
                "SUPERVISOR_STATUS: done",
                "SUPERVISOR_SUMMARY: worker finished",
                "SUPERVISOR_NEXT: review diff",
            ]
        ),
        encoding="utf-8",
    )
    append_managed_record(
        default_registry_path(codex_home),
        ManagedCodexRecord(
            record_id="managed-001",
            name="feature-a",
            cwd=str(workspace),
            prompt="PRIVATE_PROMPT_SHOULD_NOT_PASS",
            command=("codex", "exec"),
            pid=0,
            started_at="2026-05-27T00:00:00+00:00",
            log_path=str(log_path),
            backend="tmux",
            tmux_session="feature-a",
        ),
    )

    result = _runner().run_capability(
        "supervisor.worker_review",
        inputs={"codex_home": str(codex_home)},
    )

    assert result["kind"] == "capability_run_result"
    assert result["capability_id"] == "supervisor.worker_review"
    assert result["status"] == "completed"
    assert result["runner_kind"] == "deterministic_readonly"
    review = result["worker_review"]
    assert review["status"] == "ok"
    assert review["summary"]["total"] == 1
    assert review["decision_summary"]["merge_candidates"] == 1
    assert review["safety"]["auto_merge"] is False
    assert review["safety"]["delete_branch"] is False
    assert review["workers"] == [
        {
            "record_id": "managed-001",
            "name": "feature-a",
            "worker_role": "worker",
            "backend": "tmux",
            "registry_status": "launched",
            "cwd": str(workspace),
            "cwd_exists": True,
            "started_at": "2026-05-27T00:00:00+00:00",
            "worktree": {
                "exists": True,
                "branch": "supervisor/feature-a",
                "inferred_branch": None,
            },
            "supervisor_protocol": {
                "status": "done",
                "summary": "worker finished",
                "next": "review diff",
            },
            "changes": {
                "status": "unknown",
                "summary": "loop 快速状态未读取 diff",
            },
            "test_status": "skipped",
            "test_passed": None,
            "test_exit_code": None,
            "next_decision": {
                "recommendation": "review_then_merge_candidate",
                "summary": "worker 已完成且有本地改动；建议先复查 diff 并跑验证，通过后再人工合并。",
                "merge_suitable": True,
                "continue_or_split_task": False,
                "risk_level": "medium",
            },
        }
    ]
    json.dumps(result)
    for mapping in _walk_mapping(result):
        assert FORBIDDEN_RESULT_KEYS.isdisjoint(mapping)


def test_integration_review_capability_runs_existing_readonly_review(monkeypatch):
    supervisor_module = importlib.import_module("isotope.capabilities.supervisor")
    calls = []

    def stub_collect_integration_reviews(**kwargs):
        calls.append(kwargs)
        return {
            "status": "ok",
            "base_ref": "main",
            "include_unfinished": False,
            "include_missing_worktrees": False,
            "summary": {
                "total": 1,
                "merge_workers": 0,
                "ready_to_integrate": 1,
                "already_integrated": 0,
                "needs_review": 0,
                "conflict_risk": 0,
                "stale_missing_worktrees": 0,
            },
            "groups": {
                "merge_workers": [],
                "ready_to_integrate": [
                    {
                        "record_id": "managed-ready",
                        "name": "ready",
                        "cwd": "/tmp/repo/.worktrees/supervisor/ready",
                        "cwd_exists": True,
                        "branch": "supervisor/ready",
                        "worker_commit": "abc123",
                        "base_ref": "main",
                        "base_commit": "def456",
                        "main_contains_worker": False,
                        "main_has_worker_patch": False,
                        "worker_contains_main": True,
                        "dirty": False,
                        "dirty_paths": [],
                        "test_status": "skipped",
                        "test_passed": None,
                        "test_exit_code": None,
                        "supervisor_protocol": {
                            "status": "done",
                            "summary": "ready",
                            "next": "merge",
                        },
                        "merge_worker": False,
                        "merge_worker_source": None,
                        "merge_conflict": False,
                        "merge_check": {
                            "available": True,
                            "conflict": False,
                            "returncode": 0,
                            "stdout": "PRIVATE_TREE_SHOULD_NOT_PASS",
                            "stderr": "PRIVATE_STDERR_SHOULD_NOT_PASS",
                        },
                        "validation": {
                            "status": "skipped",
                            "commands": [
                                {"command": ["pytest"], "stdout_tail": "PRIVATE"}
                            ],
                        },
                        "group": "ready_to_integrate",
                        "reason": "ready",
                        "reasons": ["done"],
                    }
                ],
                "already_integrated": [],
                "needs_review": [],
                "conflict_risk": [],
            },
            "workers": [],
            "stale_missing_worktrees": [],
            "safety": {
                "auto_merge": False,
                "push": False,
                "delete_branch": False,
                "note": "只读扫描 managed worker、git 分支和提交包含关系，不执行 merge/push/delete。",
            },
        }

    monkeypatch.setattr(
        supervisor_module,
        "collect_integration_reviews",
        stub_collect_integration_reviews,
    )

    result = _runner().run_capability(
        "supervisor.integration_review",
        inputs={"codex_home": "/tmp/codex-home"},
    )

    assert calls == [
        {
            "codex_home": Path("/tmp/codex-home"),
            "base_ref": "main",
            "include_unfinished": False,
            "include_missing_worktrees": False,
            "run_test_gate": False,
            "run_candidate_validation": False,
        }
    ]
    assert result["kind"] == "capability_run_result"
    assert result["capability_id"] == "supervisor.integration_review"
    assert result["status"] == "completed"
    assert result["runner_kind"] == "deterministic_readonly"
    review = result["integration_review"]
    assert review["status"] == "ok"
    assert review["summary"]["ready_to_integrate"] == 1
    assert review["groups"]["ready_to_integrate"] == [
        {
            "record_id": "managed-ready",
            "name": "ready",
            "cwd": "/tmp/repo/.worktrees/supervisor/ready",
            "cwd_exists": True,
            "branch": "supervisor/ready",
            "worker_commit": "abc123",
            "base_ref": "main",
            "base_commit": "def456",
            "main_contains_worker": False,
            "main_has_worker_patch": False,
            "worker_contains_main": True,
            "dirty": False,
            "dirty_path_count": 0,
            "test_status": "skipped",
            "test_passed": None,
            "test_exit_code": None,
            "supervisor_protocol": {
                "status": "done",
                "summary": "ready",
                "next": "merge",
            },
            "merge_worker": False,
            "merge_worker_source": None,
            "merge_conflict": False,
            "merge_check": {
                "available": True,
                "conflict": False,
                "returncode": 0,
            },
            "validation": {"status": "skipped"},
            "group": "ready_to_integrate",
            "reason": "ready",
            "reasons": ["done"],
        }
    ]
    assert "PRIVATE_TREE_SHOULD_NOT_PASS" not in json.dumps(result)
    assert "PRIVATE_STDERR_SHOULD_NOT_PASS" not in json.dumps(result)
    assert "PRIVATE" not in json.dumps(result)
    for mapping in _walk_mapping(result):
        assert FORBIDDEN_RESULT_KEYS.isdisjoint(mapping)


def test_memory_query_capability_runs_existing_public_metadata_query(tmp_path):
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    _write_memory_record(
        memory_dir,
        MemoryRecord(
            memory_id="mem_capability",
            scope="run",
            content={"raw": "raw memory content must not leak"},
            summary="Capability runner can recall memory boundaries.",
            source_refs=[{"ref_type": "artifact", "artifact_id": "artifact_memory"}],
            provenance={
                "run_id": "run_memory",
                "execution_id": "exec_memory",
                "action_type": "write_memory",
            },
            created_at="2026-05-27T00:00:00Z",
            supersedes=[],
            quality="verified",
        ),
    )

    result = _runner().run_capability(
        "memory.query",
        inputs={
            "root": str(tmp_path),
            "query": "memory boundaries",
            "run_id": "run_memory",
            "controlled_expand": True,
            "expand_budget": 100,
        },
    )

    assert result["kind"] == "capability_run_result"
    assert result["capability_id"] == "memory.query"
    assert result["status"] == "completed"
    assert result["runner_kind"] == "deterministic_readonly"
    memory_query = result["memory_query"]
    assert memory_query["status"] == "ok"
    assert memory_query["content_policy"] == "memory_record_refs_expandable"
    assert memory_query["controlled_expand"]["status"] == "materialized"
    assert memory_query["controlled_expand"]["budget"] == 100
    assert memory_query["controlled_expand"]["content_policy"] == (
        "controlled_expand_memory_record_content_only"
    )
    assert memory_query["controlled_expand"]["materialized_results"] == [
        {
            "record_id": "mem_capability",
            "scope": "run",
            "encoding": "json",
            "materialized_text": '{"raw": "raw memory content must not leak"}',
            "used": memory_query["controlled_expand"]["used"],
            "truncated": False,
            "source_refs": [{"ref_type": "artifact", "artifact_id": "artifact_memory"}],
            "provenance": {
                "run_id": "run_memory",
                "execution_id": "exec_memory",
                "action_type": "write_memory",
            },
        }
    ]
    assert memory_query["results"] == [
        {
            "record_id": "mem_capability",
            "scope": "run",
            "summary": "Capability runner can recall memory boundaries.",
            "source_refs": [{"ref_type": "artifact", "artifact_id": "artifact_memory"}],
            "provenance": {
                "run_id": "run_memory",
                "execution_id": "exec_memory",
                "action_type": "write_memory",
            },
            "quality": "verified",
        }
    ]
    for mapping in _walk_mapping(result):
        assert FORBIDDEN_RESULT_KEYS.isdisjoint(mapping)


def test_memory_recall_capability_runs_state_root_preview_query(tmp_path):
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    _write_memory_record(
        memory_dir,
        MemoryRecord(
            memory_id="mem_recall",
            scope="run",
            content={"raw": "raw memory content must not leak"},
            summary="Capability runner can recall app-level memory previews.",
            source_refs=[{"ref_type": "artifact", "artifact_id": "artifact_memory"}],
            provenance={
                "run_id": "run_memory",
                "execution_id": "exec_memory",
                "action_type": "write_memory",
            },
            created_at="2026-06-04T00:00:00Z",
            supersedes=[],
            quality="verified",
        ),
    )

    result = _runner().run_capability(
        "memory.recall",
        inputs={
            "root": str(tmp_path),
            "query": "app-level memory previews",
            "scope": "run",
        },
    )

    assert result["kind"] == "capability_run_result"
    assert result["capability_id"] == "memory.recall"
    assert result["status"] == "completed"
    assert result["runner_kind"] == "deterministic_readonly"
    recall = result["memory_recall"]
    assert recall["status"] == "ok"
    assert recall["content_policy"] == "memory_record_refs_expandable"
    assert recall["summary"]["matched"] == 1
    assert recall["results"] == [
        {
            "record_id": "mem_recall",
            "scope": "run",
            "summary": "Capability runner can recall app-level memory previews.",
            "source_refs": [{"ref_type": "artifact", "artifact_id": "artifact_memory"}],
            "provenance": {
                "run_id": "run_memory",
                "execution_id": "exec_memory",
                "action_type": "write_memory",
            },
            "quality": "verified",
        }
    ]
    for mapping in _walk_mapping(result):
        assert FORBIDDEN_RESULT_KEYS.isdisjoint(mapping)


def test_memory_promotion_preview_capability_returns_public_metadata_proposal():
    result = _runner().run_capability(
        "memory.promotion.preview",
        inputs={
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
                "summary": "Promote research report summary into memory.",
                "provenance": {"execution_id": "exec_report"},
            },
            "scope": "session",
            "quality": "verified",
        },
    )

    assert result["kind"] == "capability_run_result"
    assert result["capability_id"] == "memory.promotion.preview"
    assert result["status"] == "completed"
    assert result["runner_kind"] == "deterministic_readonly"
    preview = result["memory_promotion_preview"]
    assert preview == {
        "action_type": "write_memory",
        "requested_capabilities": {"tools": ["write_memory"]},
        "scope": "session",
        "quality": "verified",
        "summary": "Promote research report summary into memory.",
        "source_refs": [
            {
                "ref_type": "artifact",
                "scope": "run",
                "run_id": "run_memory",
                "artifact_id": "artifact_report",
            }
        ],
        "provenance": {
            "promotion_source": "artifact",
            "source_execution_id": "exec_report",
        },
        "content_policy": "memory_record_refs_expandable",
    }
    output = json.dumps(result)
    assert "raw_content" not in output
    assert "raw memory content" not in output
    for mapping in _walk_mapping(result):
        assert FORBIDDEN_RESULT_KEYS.isdisjoint(mapping)


def test_screen_report_capability_runs_existing_public_metadata_report(tmp_path):
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

    result = _runner().run_capability(
        "screen.report",
        inputs={
            "root": str(tmp_path),
            "run_id": "run_screen",
        },
    )

    assert result["kind"] == "capability_run_result"
    assert result["capability_id"] == "screen.report"
    assert result["status"] == "completed"
    assert result["runner_kind"] == "deterministic_readonly"
    screen_report = result["screen_report"]
    assert screen_report["status"] == "ok"
    assert screen_report["summary"]["control_status"] == "planned"
    assert screen_report["summary"]["approval_required"] is True
    assert screen_report["summary"]["control_actions"][0]["action_types"] == [
        "restore_window"
    ]
    assert "raw screen control payload" not in json.dumps(result, sort_keys=True)
    for mapping in _walk_mapping(result):
        assert FORBIDDEN_RESULT_KEYS.isdisjoint(mapping)


def test_screen_observe_capability_runs_policy_gated_observe_and_reports_artifacts(
    tmp_path,
    monkeypatch,
):
    from isotope.capabilities import screen as screen_capability

    class StubScreenBackend:
        def __init__(self):
            self.calls = []

        def run(self, request):
            self.calls.append(request)
            return {
                "backend_session_id": "stub_screen_001",
                "status": "captured",
                "started_at": "2026-05-24T00:00:00Z",
                "finished_at": "2026-05-24T00:00:01Z",
                "summary": "screen observe captured",
                "output_artifacts": [
                    {
                        "artifact_type": "screen_metadata",
                        "summary": "screen metadata captured",
                        "content": json.dumps(
                            {
                                "matched_count": 1,
                                "selected_window_id": "window_001",
                                "selection_reason": "first_match",
                                "target": {
                                    "window_id": "window_001",
                                    "title": "Notes",
                                    "app": "notepad.exe",
                                    "is_minimized": False,
                                },
                            },
                            sort_keys=True,
                        ),
                    },
                    {
                        "artifact_type": "screen_screenshot",
                        "summary": "screen screenshot captured",
                        "content": "raw screenshot bytes must not leak",
                    },
                ],
                "reason_code": "screen_observe_captured",
                "retryable": False,
                "resource_usage": {"window_count": 1},
            }

    backend = StubScreenBackend()
    monkeypatch.setattr(
        screen_capability,
        "WindowsScreenBackend",
        lambda: backend,
        raising=False,
    )

    result = _runner().run_capability(
        "screen.observe",
        root_path=tmp_path,
        inputs={
            "target_selector": {
                "kind": "window",
                "selector": {"app": "notepad.exe"},
            },
            "target_allowlist": {"allowed_apps": ["notepad.exe"]},
            "capture": ["metadata", "screenshot"],
        },
    )

    assert result["kind"] == "capability_run_result"
    assert result["capability_id"] == "screen.observe"
    assert result["status"] == "completed"
    assert result["runner_kind"] == "deterministic_local"
    assert result["screen_observe"]["status"] == "completed"
    assert result["screen_observe"]["run_id"] == result["screen_report"]["run_id"]
    assert backend.calls[0].tool_name == "screen_observe"
    assert backend.calls[0].capture == ["metadata", "screenshot"]
    screen_report = result["screen_report"]
    assert screen_report["summary"]["observe_status"] == "captured"
    assert screen_report["summary"]["screenshot_available"] is True
    assert screen_report["summary"]["matched_count"] == 1
    assert screen_report["summary"]["selected_window_id"] == "window_001"
    assert "raw screenshot bytes" not in json.dumps(result, sort_keys=True)
    for mapping in _walk_mapping(result):
        assert FORBIDDEN_RESULT_KEYS.isdisjoint(mapping)


def test_screen_observe_capability_reports_backend_failure_without_artifacts(
    tmp_path,
    monkeypatch,
):
    from isotope.capabilities import screen as screen_capability

    class StubScreenBackend:
        def run(self, request):
            return {
                "backend_session_id": "stub_screen_unavailable",
                "status": "failed",
                "started_at": "2026-05-24T00:00:00Z",
                "finished_at": "2026-05-24T00:00:01Z",
                "summary": "Windows screen backend is unavailable",
                "output_artifacts": [],
                "reason_code": "screen_windows_backend_unavailable",
                "retryable": False,
                "resource_usage": {},
            }

    monkeypatch.setattr(
        screen_capability,
        "WindowsScreenBackend",
        StubScreenBackend,
        raising=False,
    )

    result = _runner().run_capability(
        "screen.observe",
        root_path=tmp_path,
        inputs={
            "target_selector": {
                "kind": "window",
                "selector": {"app": "notepad.exe"},
            },
            "target_allowlist": {"allowed_apps": ["notepad.exe"]},
            "capture": ["metadata"],
        },
    )

    assert result["status"] == "completed"
    assert result["screen_observe"]["status"] == "failed"
    assert result["screen_observe"]["failure"] == {
        "reason_code": "screen_windows_backend_unavailable",
        "message": "Windows screen backend is unavailable",
    }
    assert result["screen_report"]["summary"]["observe_status"] == "no_screen_artifacts"
    assert result["screen_report"]["summary"]["artifact_count"] == 0
    for mapping in _walk_mapping(result):
        assert FORBIDDEN_RESULT_KEYS.isdisjoint(mapping)


def test_research_search_uses_runtime_provider_policy_by_default(
    tmp_path, monkeypatch
):
    from isotope.capabilities import research as research_capability

    calls = []

    class RecordingCodexProvider:
        provider_name = "codex_delegated"

        def run(self, query):
            return {
                "research_id": "research_codex_unit",
                "query": query,
                "provider": "codex_delegated",
                "created_at": "2026-06-03T00:00:00Z",
                "status": "ok",
                "evidence_status": "complete",
                "sources": [
                    {
                        "source_id": "src_001",
                        "title": "Isotope research note",
                        "url": "https://example.com/isotope-research",
                        "snippet": "Research claims should cite source ids.",
                        "why_used": "unit test Codex provider",
                        "retrieved_at": "2026-06-03T00:00:00Z",
                    }
                ],
                "report": {
                    "summary": "Codex research summary for capacity research integration.",
                    "claims": [
                        {
                            "text": "Research claims should cite source ids.",
                            "source_ids": ["src_001"],
                            "confidence": "medium",
                        }
                    ],
                    "limitations": [],
                    "next_queries": [],
                },
                "provenance": {"provider": "codex_delegated"},
            }

    def build_provider(provider_id, **kwargs):
        calls.append({"provider_id": provider_id, **kwargs})
        return RecordingCodexProvider()

    monkeypatch.setattr(
        research_capability,
        "build_research_provider",
        build_provider,
    )

    result = _runner().run_capability(
        "research.search",
        inputs={
            "root": str(tmp_path),
            "query": "capacity research integration",
        },
    )

    assert result["kind"] == "capability_run_result"
    assert result["capability_id"] == "research.search"
    assert result["status"] == "completed"
    assert result["runner_kind"] == "deterministic_local"
    research_search = result["research_search"]
    assert research_search["status"] == "ok"
    assert research_search["query"] == "capacity research integration"
    assert research_search["provider"] == "codex_delegated"
    assert research_search["evidence_status"] == "complete"
    assert research_search["source_count"] == 1
    assert calls == [{"provider_id": "codex", "workspace_root": str(tmp_path)}]
    assert (
        research_search["report_summary"]
        == "Codex research summary for capacity research integration."
    )
    assert research_search["source_previews"] == [
        {
            "source_id": "src_001",
            "title": "Isotope research note",
            "url": "https://example.com/isotope-research",
            "snippet": "Research claims should cite source ids.",
            "why_used": "unit test Codex provider",
        }
    ]
    assert [item["artifact_type"] for item in research_search["artifacts"]] == [
        "research.raw_transcript",
        "research.report",
    ]
    assert "research" not in result
    for mapping in _walk_mapping(result):
        assert FORBIDDEN_RESULT_KEYS.isdisjoint(mapping)


def test_research_search_private_tavily_policy_uses_research_flow_artifacts(
    tmp_path, monkeypatch
):
    from isotope.capabilities import research as research_capability

    calls = []

    class RecordingTavilyProvider:
        provider_name = "tavily"

        def run(self, query):
            return {
                "research_id": "research_tavily_unit",
                "query": query,
                "provider": "tavily",
                "created_at": "2026-06-03T00:00:00Z",
                "status": "ok",
                "evidence_status": "complete",
                "sources": [
                    {
                        "source_id": "src_001",
                        "title": "Isotope research note",
                        "url": "https://example.com/research-note",
                        "snippet": "Research claims should cite source-backed snippets.",
                        "why_used": "unit test Tavily provider",
                        "retrieved_at": "2026-06-03T00:00:00Z",
                    }
                ],
                "report": {
                    "summary": "Tavily research summary.",
                    "claims": [
                        {
                            "text": "Research claims should cite source-backed snippets.",
                            "source_ids": ["src_001"],
                            "confidence": "medium",
                        }
                    ],
                    "limitations": [],
                    "next_queries": [],
                },
                "provenance": {"provider": "tavily"},
            }

    def build_provider(provider_id, **kwargs):
        calls.append({"provider_id": provider_id, **kwargs})
        return RecordingTavilyProvider()

    monkeypatch.setattr(
        research_capability,
        "build_research_provider",
        build_provider,
    )

    result = research_capability.run_research_search(
        inputs={
            "root": str(tmp_path),
            "query": "capacity research integration",
            "provider": "tavily",
            "allow_network": True,
            "tavily_max_results": 3,
        },
    )

    assert calls == [
        {
            "provider_id": "tavily",
            "workspace_root": str(tmp_path),
            "tavily_enable_network": True,
            "tavily_max_results": 3,
        }
    ]
    research_search = result["research_search"]
    assert research_search["provider"] == "tavily"
    assert research_search["source_count"] == 1
    assert [item["artifact_type"] for item in research_search["artifacts"]] == [
        "research.raw_transcript",
        "research.report",
    ]
    for mapping in _walk_mapping(result):
        assert FORBIDDEN_RESULT_KEYS.isdisjoint(mapping)


def test_research_search_tavily_exact_url_returns_extract_summary(
    tmp_path, monkeypatch
):
    from isotope.capabilities import research as research_capability

    class ExactUrlTavilyProvider:
        provider_name = "tavily"

        def run(self, query):
            return {
                "research_id": "research_exact_url_unit",
                "query": query,
                "provider": "tavily",
                "created_at": "2026-06-03T00:00:00Z",
                "status": "ok",
                "evidence_status": "complete",
                "sources": [
                    {
                        "source_id": "src_001",
                        "title": "Exact URL Article",
                        "url": query,
                        "snippet": "真实 URL 正文片段，可直接用于总结。",
                        "why_used": "Exact URL content fetched for the user-provided URL.",
                        "retrieved_at": "2026-06-03T00:00:00Z",
                        "provider_rank": 1,
                    }
                ],
                "report": {
                    "summary": "真实 URL 正文摘要，包含页面实际内容。",
                    "claims": [
                        {
                            "text": "真实 URL 正文片段，可直接用于总结。",
                            "source_ids": ["src_001"],
                            "confidence": "medium",
                        }
                    ],
                    "limitations": [],
                    "next_queries": [],
                },
                "provenance": {"provider": "tavily", "tavily": {"mode": "exact_url_fetch"}},
            }

    monkeypatch.setattr(
        research_capability,
        "build_research_provider",
        lambda provider_id, **kwargs: ExactUrlTavilyProvider(),
    )

    result = research_capability.run_research_search(
        inputs={
            "root": str(tmp_path),
            "query": "https://example.com/exact-url",
            "provider": "tavily",
            "allow_network": True,
        },
    )

    research_search = result["research_search"]
    assert research_search["provider"] == "tavily"
    assert research_search["report_summary"] == "真实 URL 正文摘要，包含页面实际内容。"
    assert research_search["source_previews"] == [
        {
            "source_id": "src_001",
            "title": "Exact URL Article",
            "url": "https://example.com/exact-url",
            "snippet": "真实 URL 正文片段，可直接用于总结。",
            "why_used": "Exact URL content fetched for the user-provided URL.",
            "provider_rank": 1,
        }
    ]
    assert "raw_content" not in json.dumps(result, ensure_ascii=False)


def test_research_search_default_policy_uses_research_flow_artifacts(
    tmp_path, monkeypatch
):
    from isotope.capabilities import research as research_capability

    calls = []

    class RecordingCodexProvider:
        provider_name = "codex_delegated"

        def run(self, query):
            return {
                "research_id": "research_codex_unit",
                "query": query,
                "provider": "codex_delegated",
                "created_at": "2026-06-03T00:00:00Z",
                "status": "ok",
                "evidence_status": "complete",
                "sources": [
                    {
                        "source_id": "src_001",
                        "title": "Codex delegated source",
                        "url": "https://example.com/codex-source",
                        "snippet": "Codex delegated research returns cited snippets.",
                        "why_used": "unit test Codex provider",
                        "retrieved_at": "2026-06-03T00:00:00Z",
                    }
                ],
                "report": {
                    "summary": "Codex delegated research summary.",
                    "claims": [
                        {
                            "text": "Codex delegated research returns cited snippets.",
                            "source_ids": ["src_001"],
                            "confidence": "medium",
                        }
                    ],
                    "limitations": [],
                    "next_queries": [],
                },
                "provenance": {"provider": "codex_delegated"},
            }

    def build_provider(provider_id, **kwargs):
        calls.append({"provider_id": provider_id, **kwargs})
        return RecordingCodexProvider()

    monkeypatch.setattr(
        research_capability,
        "build_research_provider",
        build_provider,
    )

    result = _runner().run_capability(
        "research.search",
        inputs={
            "root": str(tmp_path),
            "query": "capacity research integration",
        },
    )

    assert calls == [
        {
            "provider_id": "codex",
            "workspace_root": str(tmp_path),
        }
    ]
    research_search = result["research_search"]
    assert research_search["provider"] == "codex_delegated"
    assert research_search["source_count"] == 1
    assert [item["artifact_type"] for item in research_search["artifacts"]] == [
        "research.raw_transcript",
        "research.report",
    ]
    for mapping in _walk_mapping(result):
        assert FORBIDDEN_RESULT_KEYS.isdisjoint(mapping)


def test_research_promote_capability_builds_public_metadata_proposal_summary(tmp_path):
    store = ArtifactStore(tmp_path)
    artifact = store.create_artifact(
        "run_research",
        execution_id="exec_research",
        artifact_type="research.report",
        summary="Stub research summary for capacity promotion.",
        content=json.dumps(
            {
                "evidence_status": "complete",
                "sources": [{"source_id": "src_001", "title": "Source"}],
                "report": {
                    "summary": "raw report body must not leak through capability",
                    "claims": [
                        {"text": "Source-backed claim.", "source_ids": ["src_001"]}
                    ],
                },
            },
            sort_keys=True,
        ),
    )

    result = _runner().run_capability(
        "research.promote",
        inputs={
            "root": str(tmp_path),
            "run_id": "run_research",
            "artifact_id": artifact.artifact_id,
            "agent_id": "agent_capacity",
            "thread_id": "thread_capacity",
            "scope": "session",
            "quality": "candidate",
            "proposal_id": "prop_capacity_research",
        },
    )

    assert result["kind"] == "capability_run_result"
    assert result["capability_id"] == "research.promote"
    assert result["status"] == "completed"
    assert result["runner_kind"] == "deterministic_local"
    promotion = result["research_promotion"]
    assert promotion == {
        "status": "ok",
        "artifact_type": "research.report",
        "artifact_ref": artifact.ref.to_dict(),
        "proposal_id": "prop_capacity_research",
        "action_type": "write_memory",
        "scope": "session",
        "quality": "candidate",
        "summary": "Stub research summary for capacity promotion.",
        "source_refs": [artifact.ref.to_dict()],
        "requested_capabilities": {"tools": ["write_memory"]},
        "quality_gate_status": "promotable",
        "quality_gate_reasons": [],
        "memory_write": "proposal_only",
    }
    output = json.dumps(result, sort_keys=True)
    assert "raw report body" not in output
    for mapping in _walk_mapping(result):
        assert FORBIDDEN_RESULT_KEYS.isdisjoint(mapping)


def _write_memory_record(memory_dir, record: MemoryRecord) -> None:
    (memory_dir / f"{record.memory_id}.json").write_text(
        json.dumps(asdict(record), sort_keys=True),
        encoding="utf-8",
    )
