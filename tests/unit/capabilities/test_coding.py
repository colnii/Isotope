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

def test_runner_discovers_coding_task_plan_from_default_catalog():
    runner = _runner()

    assert "coding_task.plan" in _ids(runner.list_capabilities())
    assert "coding_task.preview" not in _ids(runner.list_capabilities())
    search = runner.search_capabilities(query="native coding")

    assert "coding_task.plan" in _ids(search["capabilities"])
    description = runner.describe_capability("coding_task.plan")
    assert description["input_contract"]["required"] == ["root", "cwd", "goal"]
    assert description["input_contract"]["properties"]["allowed_paths"]["type"] == "array"
    assert (
        description["input_contract"]["properties"]["verification_commands"]["type"]
        == "array"
    )
    assert "isolated_workspace_execution_path" in description["safety_boundaries"]
    assert "reviewed_apply_handoff" in description["safety_boundaries"]



def test_runner_builds_coding_task_plan(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    root = tmp_path / "state"

    result = _runner().run_capability(
        "coding_task.plan",
        inputs={
            "root": str(root),
            "cwd": str(workspace),
            "goal": "Add a native code edit action.",
            "allowed_paths": ["src/isotope/capabilities"],
            "verification_commands": ["pytest tests/unit/capabilities -q"],
        },
    )

    assert result["kind"] == "capability_run_result"
    assert result["capability_id"] == "coding_task.plan"
    assert result["status"] == "completed"
    assert result["runner_kind"] == "native_coding_plan"
    assert result["plan"]["goal"] == "Add a native code edit action."
    assert result["plan"]["cwd_status"] == "exists"
    assert result["plan"]["execution_mode"] == "isolated_workspace_execution"
    assert result["plan"]["execution_requirements"] == [
        "policy_granted_writable_workspace",
        "controlled_code_read_search",
        "structured_patch_application",
        "allowlisted_test_execution",
        "artifact_backed_diff_and_changed_files",
        "optional_vcs_adapter",
    ]
    assert result["plan"]["next_capabilities"] == [
        "coding_task.execute",
        "coding_task.apply_reviewed_diff",
    ]
    assert not list(root.rglob("*"))



def test_coding_task_plan_rejects_malformed_path_lists(tmp_path):
    with pytest.raises(ValueError, match="allowed_paths"):
        _runner().run_capability(
            "coding_task.plan",
            inputs={
                "root": str(tmp_path / "state"),
                "cwd": str(tmp_path),
                "goal": "Edit code.",
                "allowed_paths": "src",
            },
        )



def test_coding_task_plan_reports_missing_cwd_without_creating_it(tmp_path):
    missing = tmp_path / "missing"

    result = _runner().run_capability(
        "coding_task.plan",
        inputs={
            "root": str(tmp_path / "state"),
            "cwd": str(missing),
            "goal": "Edit code.",
        },
    )

    assert result["plan"]["cwd_status"] == "missing"
    assert not missing.exists()



def test_coding_task_plan_stops_when_required_inputs_are_missing():
    plan = _runner().plan_capability_run(
        "coding_task.plan",
        inputs={"cwd": "/tmp/project"},
    )

    assert plan["can_launch"] is False
    assert plan["status"] == "missing_inputs"
    assert plan["runner_kind"] == "native_coding_plan"
    assert plan["missing_inputs"] == ["root", "goal"]
    assert plan["scenario"] is None



def test_coding_task_plan_is_launchable_with_required_inputs(tmp_path):
    plan = _runner().plan_capability_run(
        "coding_task.plan",
        inputs={
            "root": str(tmp_path / "state"),
            "cwd": str(tmp_path),
            "goal": "Plan native coding.",
        },
    )

    assert plan["can_launch"] is True
    assert plan["status"] == "launchable"
    assert plan["runner_kind"] == "native_coding_plan"
    assert plan["blocking_reasons"] == []
    assert "isolated_workspace_execution_path" in plan["safety_boundaries"]



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
    assert execution["artifact_refs"]["diff_result"]["ref_type"] == "artifact"
    assert sorted(artifact.artifact_type for artifact in artifacts) == [
        "native_coding.changed_files",
        "native_coding.diff_result",
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



