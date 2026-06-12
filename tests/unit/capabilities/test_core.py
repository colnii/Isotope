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

import subprocess
from pathlib import Path


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



def test_runner_plans_mcp_capabilities_as_missing_inputs():
    runner = _runner()

    plan = runner.plan_capability_run("mcp.tool.call", inputs={})

    assert plan["status"] == "missing_inputs"
    assert plan["missing_inputs"] == ["server_id", "tool_name"]
    assert plan["can_launch"] is False



def test_runner_describe_returns_public_metadata_catalog_metadata():
    description = _runner().describe_capability("artifact.review")

    assert description["capability_id"] == "artifact.review"
    assert description["shelf"] == "product_candidate"
    assert "input_contract" in description
    assert "output_contract" in description
    json.dumps(description)
    for mapping in _walk_mapping(description):
        assert FORBIDDEN_RESULT_KEYS.isdisjoint(mapping)



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
    assert materialized["event_append"] == "state_event_append_handoff"
    assert (workspace_root / "src" / "app.py").read_text(encoding="utf-8") == "print('native')\n"
    assert (workspace_root / "README.md").read_text(encoding="utf-8") == "hello\n"
    assert not (workspace_root / "src" / "skip.py").exists()
    assert not (workspace_root / ".git").exists()
    assert not (workspace_root / ".venv").exists()
    assert (source / "src" / "app.py").read_text(encoding="utf-8") == "print('native')\n"



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
    assert result["runner_kind"] == "deterministic_projection"
    assert changed["status"] == "changed"
    assert changed["workspace_id"] == "workspace_native_coding_slice_9"
    assert changed["changed_file_count"] == 3
    assert changed["changed_files"] == [
        {"path": "src/app.py", "status": "modified"},
        {"path": "src/delete.py", "status": "deleted"},
        {"path": "src/new.py", "status": "added"},
    ]
    assert changed["artifact_write"] == "artifact_write_action_handoff"
    assert changed["content_policy"] == "diff_result_projection"



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
    assert released["event_append"] == "state_event_append_handoff"
    assert not workspace_root.exists()
    assert (source / "keep.py").read_text(encoding="utf-8") == "source\n"



def test_runner_discovers_artifact_diff_result_and_changed_files_from_default_catalog():
    runner = _runner()

    assert "artifact.diff_result" in _ids(runner.list_capabilities())
    assert "artifact.changed_files" in _ids(
        runner.search_capabilities(query="artifact changed files")["capabilities"]
    )

    diff_description = runner.describe_capability("artifact.diff_result")
    changed_description = runner.describe_capability("artifact.changed_files")
    required = ["root", "cwd", "workspace_id", "run_id", "execution_id"]
    assert diff_description["input_contract"]["required"] == required
    assert changed_description["input_contract"]["required"] == required
    assert "artifact_store_write" in diff_description["safety_boundaries"]
    assert "state_event_append_handoff" in changed_description["safety_boundaries"]



def test_artifact_output_manifests_use_event_handoff_language():
    descriptions = {
        "diff": _runner().describe_capability("artifact.diff_result"),
        "changed": _runner().describe_capability("artifact.changed_files"),
    }
    manifest_text = json.dumps(descriptions, ensure_ascii=False)
    forbidden_terms = [
        "no" + "_event" + "_append",
    ]

    for description in descriptions.values():
        assert "artifact_store_write" in description["safety_boundaries"]
        assert "state_event_append_handoff" in description["safety_boundaries"]
    for term in forbidden_terms:
        assert term not in manifest_text



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
    assert artifact["event_append"] == "state_event_append_handoff"
    assert content["changed_file_count"] == 2
    assert content["event_append"] == "state_event_append_handoff"
    assert content["changed_files"] == [
        {"path": "src/app.py", "status": "modified"},
        {"path": "src/new.py", "status": "added"},
    ]
    assert "secret" not in json.dumps(content)



def test_runner_writes_diff_result_artifact_without_raw_file_content(tmp_path):
    source = tmp_path / "repo"
    (source / "src").mkdir(parents=True)
    (source / "src" / "app.py").write_text("old raw content\n", encoding="utf-8")
    root = tmp_path / "state"
    workspace_root = root / "workspaces" / "workspace_native_coding_slice_10"
    (workspace_root / "src").mkdir(parents=True)
    (workspace_root / "src" / "app.py").write_text("new raw content\n", encoding="utf-8")

    result = _runner().run_capability(
        "artifact.diff_result",
        inputs={
            "root": str(root),
            "cwd": str(source),
            "workspace_id": "workspace_native_coding_slice_10",
            "run_id": "run_native_coding",
            "execution_id": "execution_diff_result",
            "include_paths": ["src"],
        },
    )

    artifact = result["artifact"]
    metadata = ArtifactStore(root).get_metadata(artifact["artifact_id"])
    content_text = ArtifactStore(root).get_content(artifact["artifact_id"])
    content = json.loads(content_text)
    assert artifact["artifact_type"] == "native_coding.diff_result"
    assert artifact["event_append"] == "state_event_append_handoff"
    assert metadata["summary"] == "1 changed file in workspace_native_coding_slice_10"
    assert content["result_lines"] == ["modified src/app.py"]
    assert content["content_policy"] == "diff_result_projection"
    assert content["event_append"] == "state_event_append_handoff"
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
    assert "workspace_code_projection" in search_description["safety_boundaries"]



def test_code_access_manifests_use_projection_language():
    descriptions = {
        "read": _runner().describe_capability("code.read"),
        "search": _runner().describe_capability("code.search"),
    }
    manifest_text = json.dumps(descriptions, ensure_ascii=False)
    forbidden_terms = [
        "no" + "_filesystem" + "_write",
        "no" + "_command" + "_execution",
    ]

    for description in descriptions.values():
        assert "workspace_code_projection" in description["safety_boundaries"]
        assert "code_excerpt_projection" in description["safety_boundaries"]
    for term in forbidden_terms:
        assert term not in manifest_text



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
    assert result["runner_kind"] == "deterministic_projection"
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
    assert result["runner_kind"] == "deterministic_projection"
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
    assert plan["runner_kind"] == "deterministic_projection"
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



def test_terminal_exec_capacity_yolo_runs_crud_command_in_workspace_tmp(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state_root = tmp_path / "state"

    result = _runner().run_capability(
        "terminal.exec",
        inputs={
            "root": str(state_root),
            "cwd": str(workspace),
            "argv": [
                "python3",
                "-c",
                (
                    "from pathlib import Path\n"
                    "p=Path('tmp/terminal-capacity.txt')\n"
                    "p.parent.mkdir(exist_ok=True)\n"
                    "p.write_text('created', encoding='utf-8')\n"
                    "assert p.read_text(encoding='utf-8') == 'created'\n"
                    "p.write_text('updated', encoding='utf-8')\n"
                    "assert p.read_text(encoding='utf-8') == 'updated'\n"
                    "p.unlink()\n"
                    "assert not p.exists()\n"
                ),
            ],
            "approval_mode": "yolo",
        },
    )

    assert result["kind"] == "capability_run_result"
    assert result["capability_id"] == "terminal.exec"
    assert result["status"] == "completed"
    assert result["runner_kind"] == "runtime_terminal"
    terminal = result["terminal_exec"]
    assert terminal["status"] == "completed"
    assert terminal["argv0"] == "python3"
    assert terminal["approval_mode"] == "yolo"
    assert terminal["artifact_ref"]["ref_type"] == "artifact"
    assert not (workspace / "tmp" / "terminal-capacity.txt").exists()
    json.dumps(result)
    for mapping in _walk_mapping(result):
        assert FORBIDDEN_RESULT_KEYS.isdisjoint(mapping)



def test_terminal_exec_capacity_allowlist_request_creates_visible_pending_approval(tmp_path):
    from isotope.features.supervisor.desktop_snapshot import build_desktop_snapshot
    from isotope.runtime.in_process import InProcessServer

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state_root = tmp_path / "state"

    result = _runner().run_capability(
        "terminal.exec",
        inputs={
            "root": str(state_root),
            "cwd": str(workspace),
            "argv": [
                "python3",
                "-c",
                (
                    "from pathlib import Path; "
                    "p=Path('tmp/pending.txt'); "
                    "p.parent.mkdir(exist_ok=True); "
                    "p.write_text('ok')"
                ),
            ],
            "approval_mode": "allowlist",
            "allowed_commands": ["printf"],
        },
    )

    assert result["status"] == "pending_user_approval"
    terminal = result["terminal_exec"]
    assert terminal["status"] == "pending_user_approval"
    assert terminal["approval_id"]
    assert terminal["argv0"] == "python3"
    assert not (workspace / "tmp" / "pending.txt").exists()

    snapshot = build_desktop_snapshot(state_root=state_root)
    assert snapshot["counts"]["approvals"] == 1
    approval = snapshot["approvals"][0]
    assert approval["id"] == terminal["approval_id"]
    assert approval["requestedActionSummary"]["tool"] == "terminal_exec"
    assert approval["requestedActionSummary"]["terminal_command"] == "python3"

    resolved = InProcessServer(state_root).resolve_approval(
        terminal["approval_id"],
        {
            "resolution": "approved",
            "reason": "test approved terminal command",
            "resolver": "pytest",
        },
    )

    assert resolved["status"] == "completed"
    assert (workspace / "tmp" / "pending.txt").read_text(encoding="utf-8") == "ok"



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
    assert "git_status_projection" in status_description["safety_boundaries"]
    assert "git_diff_projection" in diff_description["safety_boundaries"]
    assert "diff_result_projection" in diff_description["safety_boundaries"]



def test_vcs_status_and_diff_manifests_use_projection_language():
    runner = _runner()
    manifest_text = json.dumps(
        {
            "status": runner.describe_capability("vcs.status"),
            "diff": runner.describe_capability("vcs.diff"),
        },
        ensure_ascii=False,
    )
    forbidden_terms = [
        "read" + "_snapshot",
        "inspec" + "tion",
        "只读" + "扫描",
        "不" + "执行",
    ]

    assert "git_status_projection" in manifest_text
    assert "git_diff_projection" in manifest_text
    for term in forbidden_terms:
        assert term not in manifest_text



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
    assert result["runner_kind"] == "deterministic_projection"
    assert status["status"] == "dirty"
    assert status["branch"] in {"master", "main"}
    assert status["changed_files"] == [
        {"path": "app.py", "index_status": " ", "worktree_status": "M"},
        {"path": "new.py", "index_status": "?", "worktree_status": "?"},
    ]
    assert status["changed_file_count"] == 2
    assert status["artifact_write"] == "not_performed"
    assert not list(root.rglob("*"))



def test_runner_reports_git_diff_result_and_changed_files(tmp_path):
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
    assert result["runner_kind"] == "deterministic_projection"
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
    assert plan["runner_kind"] == "deterministic_projection"
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
    assert plan["runner_kind"] == "deterministic_projection"
    assert plan["missing_inputs"] == ["state_root", "query"]
    assert plan["scenario"] is None



def test_worker_review_plan_stops_when_required_inputs_are_missing():
    plan = _runner().plan_capability_run("supervisor.worker_review", inputs={})

    assert plan["can_launch"] is False
    assert plan["status"] == "missing_inputs"
    assert plan["runner_kind"] == "deterministic_projection"
    assert plan["missing_inputs"] == ["state_root"]
    assert plan["scenario"] is None



def test_integration_review_plan_stops_when_required_inputs_are_missing():
    plan = _runner().plan_capability_run("supervisor.integration_review", inputs={})

    assert plan["can_launch"] is False
    assert plan["status"] == "missing_inputs"
    assert plan["runner_kind"] == "deterministic_projection"
    assert plan["missing_inputs"] == ["state_root"]
    assert plan["scenario"] is None



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



def test_request_context_capability_runs_existing_context_search(tmp_path):
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
    assert result["runner_kind"] == "deterministic_projection"
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
    assert result["runner_kind"] == "deterministic_projection"
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



def test_integration_review_capability_runs_existing_review_collection(monkeypatch):
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
                "note": "扫描 managed worker、git 分支和提交包含关系；合并、推送、清理由后续工单执行。",
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
    assert result["runner_kind"] == "deterministic_projection"
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

