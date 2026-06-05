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

def test_runner_discovers_workspace_isolated_rw_from_default_catalog():
    runner = _runner()

    assert "workspace.isolated_rw" in _ids(runner.list_capabilities())
    search = runner.search_capabilities(query="isolated writable workspace")

    assert "workspace.isolated_rw" in _ids(search["capabilities"])
    description = runner.describe_capability("workspace.isolated_rw")
    assert description["input_contract"]["required"] == ["root", "cwd", "workspace_name"]
    assert description["input_contract"]["properties"]["allowed_paths"]["type"] == "array"
    assert "workspace_action_handoff" in description["safety_boundaries"]
    assert "path_traversal_rejected" in description["safety_boundaries"]



def test_workspace_isolated_rw_manifest_uses_action_handoff_language():
    description = _runner().describe_capability("workspace.isolated_rw")
    manifest_text = json.dumps(description, ensure_ascii=False)
    forbidden_terms = [
        "proposal" + "_only",
        "no" + "_filesystem" + "_write",
        "workspace" + "_proposal",
        "no" + "_workspace" + "_materialization",
        "no" + "_git" + "_worktree" + "_creation",
    ]

    assert "workspace_action_handoff" in description["safety_boundaries"]
    assert "workspace_materialize_action_path" in description["safety_boundaries"]
    for term in forbidden_terms:
        assert term not in manifest_text



def test_runner_runs_workspace_isolated_rw_action_handoff(tmp_path):
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

    action = result["workspace_action"]
    assert result["kind"] == "capability_run_result"
    assert result["capability_id"] == "workspace.isolated_rw"
    assert result["status"] == "completed"
    assert result["runner_kind"] == "deterministic_action_handoff"
    assert action["mode"] == "isolated_rw"
    assert action["execution_mode"] == "workspace_action_handoff"
    assert action["workspace_id"] == "workspace_native_coding_slice_2"
    assert action["cwd_status"] == "exists"
    assert action["root_ref"] == "workspace://workspace_native_coding_slice_2/isolated_rw"
    assert action["allowed_paths"] == [
        "src/isotope/capabilities",
        "tests/unit/capabilities",
    ]
    assert action["forbidden_paths"] == ["src/isotope/features/supervisor"]
    assert action["next_required_capabilities"] == []
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
    assert plan["runner_kind"] == "deterministic_action_handoff"
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
    assert "lease_event_append_handoff" in description["safety_boundaries"]
    assert "workspace_materialize_action_path" in description["safety_boundaries"]



def test_workspace_lease_create_manifest_uses_event_handoff_language():
    description = _runner().describe_capability("workspace.lease_create")
    manifest_text = json.dumps(description, ensure_ascii=False)
    forbidden_terms = [
        "event" + "_candidate" + "_only",
        "no" + "_event" + "_append",
        "no" + "_filesystem" + "_write",
        "no" + "_workspace" + "_materialization",
        "without " + "appending",
    ]

    assert "lease_event_append_handoff" in description["safety_boundaries"]
    assert "workspace_materialize_action_path" in description["safety_boundaries"]
    for term in forbidden_terms:
        assert term not in manifest_text



def test_runner_runs_workspace_lease_create_event_append_handoff(tmp_path):
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
    assert result["runner_kind"] == "deterministic_action_handoff"
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
    assert plan["runner_kind"] == "deterministic_action_handoff"
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
    assert "state_root_workspace_write" in description["safety_boundaries"]
    assert "state_event_append_handoff" in description["safety_boundaries"]



def test_workspace_materialize_manifest_uses_state_write_language():
    description = _runner().describe_capability("workspace.materialize")
    manifest_text = json.dumps(description, ensure_ascii=False)
    forbidden_terms = [
        "no" + "_event" + "_append",
        "no" + "_command" + "_execution",
        "no" + "_vcs" + "_mutation",
        "without " + "appending events",
    ]

    assert "state_root_workspace_write" in description["safety_boundaries"]
    assert "state_event_append_handoff" in description["safety_boundaries"]
    for term in forbidden_terms:
        assert term not in manifest_text



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
    assert "diff_result_projection" in changed_description["safety_boundaries"]
    assert "deletes_only_materialized_workspace" in release_description["safety_boundaries"]
    assert "artifact_write_action_handoff" in changed_description["safety_boundaries"]
    assert "state_event_append_handoff" in release_description["safety_boundaries"]



def test_workspace_file_manifests_use_action_handoff_language():
    changed_description = _runner().describe_capability("workspace.changed_files")
    release_description = _runner().describe_capability("workspace.release")
    manifest_text = json.dumps(
        {
            "changed_files": changed_description,
            "release": release_description,
        },
        ensure_ascii=False,
    )
    forbidden_terms = [
        "no" + "_filesystem" + "_write",
        "no" + "_artifact" + "_write",
        "no" + "_event" + "_append",
        "no" + "_source" + "_workspace" + "_write",
    ]

    assert "artifact_write_action_handoff" in changed_description["safety_boundaries"]
    assert "state_event_append_handoff" in changed_description["safety_boundaries"]
    assert "source_workspace_preserved" in release_description["safety_boundaries"]
    for term in forbidden_terms:
        assert term not in manifest_text



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
    assert plan["runner_kind"] == "deterministic_projection"
    assert plan["missing_inputs"] == ["root", "workspace_id"]
    assert plan["scenario"] is None



