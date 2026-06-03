import importlib
import json
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
        "safety_boundaries": ("low_sensitive_manifest_only",),
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


def test_runner_describe_returns_low_sensitive_catalog_metadata():
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
    assert "workspace_read_only" in description["safety_boundaries"]
    assert "writes_existing_supervisor_context_store" in description["safety_boundaries"]


def test_runner_discovers_supervisor_worker_review_from_default_catalog():
    runner = _runner()

    assert "supervisor.worker_review" in _ids(runner.list_capabilities())
    search = runner.search_capabilities(query="worker-review")

    assert _ids(search["capabilities"]) == ["supervisor.worker_review"]
    description = runner.describe_capability("supervisor.worker_review")
    assert description["input_contract"]["required"] == ["state_root"]
    assert "codex_home" not in description["input_contract"]["properties"]
    assert "workspace_read_only" in description["safety_boundaries"]
    assert "no_merge_or_cleanup" in description["safety_boundaries"]


def test_runner_discovers_supervisor_integration_review_from_default_catalog():
    runner = _runner()

    assert "supervisor.integration_review" in _ids(runner.list_capabilities())
    search = runner.search_capabilities(query="integration-review")

    assert _ids(search["capabilities"]) == ["supervisor.integration_review"]
    description = runner.describe_capability("supervisor.integration_review")
    assert description["input_contract"]["required"] == ["state_root"]
    assert "codex_home" not in description["input_contract"]["properties"]
    assert "workspace_read_only" in description["safety_boundaries"]
    assert "no_merge_push_or_cleanup" in description["safety_boundaries"]


def test_runner_discovers_memory_query_from_default_catalog():
    runner = _runner()

    assert "memory.query" in _ids(runner.list_capabilities())
    search = runner.search_capabilities(query="memory")

    assert "memory.query" in _ids(search["capabilities"])
    description = runner.describe_capability("memory.query")
    assert description["input_contract"]["required"] == ["root", "query", "run_id"]
    assert "memory_query_grant_gated" in description["safety_boundaries"]
    assert "summary_refs_provenance_only" in description["safety_boundaries"]


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
    assert "proposal_preview_only" in description["safety_boundaries"]
    assert "no_memory_write" in description["safety_boundaries"]


def test_runner_discovers_screen_report_from_default_catalog():
    runner = _runner()

    assert "screen.report" in _ids(runner.list_capabilities())
    search = runner.search_capabilities(query="screen report")

    assert _ids(search["capabilities"]) == ["screen.report"]
    description = runner.describe_capability("screen.report")
    assert description["input_contract"]["required"] == ["root", "run_id"]
    assert "screen_artifact_read_only" in description["safety_boundaries"]
    assert "low_sensitive_summary_only" in description["safety_boundaries"]


def test_runner_discovers_research_search_from_default_catalog():
    runner = _runner()

    assert "research.search" in _ids(runner.list_capabilities())
    search = runner.search_capabilities(query="research search")

    assert _ids(search["capabilities"]) == ["research.search"]
    description = runner.describe_capability("research.search")
    assert description["input_contract"]["required"] == ["root", "query"]
    assert description["input_contract"]["properties"]["provider"]["enum"] == [
        "fake",
        "codex",
        "tavily",
    ]
    assert "provider_gate" in description["input_contract"]["properties"]
    assert "allow_network" in description["input_contract"]["properties"]
    assert "reuses_research_flow" in description["safety_boundaries"]
    assert "explicit_provider_gate" in description["safety_boundaries"]


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
    assert "preview_only_no_workspace_write" in description["safety_boundaries"]


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
    assert result["preview"]["execution_mode"] == "preview_only"
    assert result["preview"]["native_coding_requirements"] == [
        "policy_granted_writable_workspace",
        "controlled_code_read_search",
        "structured_patch_application",
        "allowlisted_test_execution",
        "artifact_backed_diff_and_changed_files",
        "optional_vcs_adapter",
    ]
    assert result["preview"]["blocked_capabilities"] == [
        "workspace.lease_create",
        "workspace.materialize",
        "workspace.changed_files",
        "workspace.release",
        "code.read",
        "code.search",
        "code.apply_patch",
        "test.run",
        "vcs.status",
        "vcs.diff",
    ]
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
    assert "preview_only_no_workspace_write" in plan["safety_boundaries"]


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
    assert proposal["next_required_capabilities"] == [
        "workspace.lease_create",
        "workspace.materialize",
        "workspace.changed_files",
        "workspace.release",
    ]
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


@pytest.mark.parametrize("provider", ["codex", "tavily"])
def test_research_search_plan_rejects_real_provider_without_provider_gate(provider):
    with pytest.raises(ValueError, match="provider_gate"):
        _runner().plan_capability_run(
            "research.search",
            inputs={
                "root": "/tmp/isotope-runtime",
                "query": "capacity research integration",
                "provider": provider,
            },
        )


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
            "backend": "tmux",
            "registry_status": "launched",
            "cwd": str(workspace),
            "cwd_exists": True,
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

    def fake_collect_integration_reviews(**kwargs):
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
        fake_collect_integration_reviews,
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


def test_memory_query_capability_runs_existing_low_sensitive_query(tmp_path):
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
    assert memory_query["content_policy"] == "summary_refs_provenance_only"
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


def test_memory_promotion_preview_capability_returns_low_sensitive_proposal():
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
        "content_policy": "summary_refs_provenance_only",
    }
    output = json.dumps(result)
    assert "raw_content" not in output
    assert "raw memory content" not in output
    for mapping in _walk_mapping(result):
        assert FORBIDDEN_RESULT_KEYS.isdisjoint(mapping)


def test_screen_report_capability_runs_existing_low_sensitive_report(tmp_path):
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


def test_research_search_capability_runs_existing_fake_research_flow(tmp_path):
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
    assert research_search["provider"] == "fake"
    assert research_search["evidence_status"] == "complete"
    assert research_search["source_count"] == 1
    assert (
        research_search["report_summary"]
        == "Fake research summary for capacity research integration."
    )
    assert research_search["source_previews"] == [
        {
            "source_id": "src_001",
            "title": "Fake source-backed research note",
            "url": "https://example.com/isotope-research",
            "snippet": "Research claims should cite source ids.",
            "why_used": "deterministic fake source for tests",
            "provider_rank": 1,
        }
    ]
    assert [item["artifact_type"] for item in research_search["artifacts"]] == [
        "research.raw_transcript",
        "research.report",
    ]
    assert "research" not in result
    for mapping in _walk_mapping(result):
        assert FORBIDDEN_RESULT_KEYS.isdisjoint(mapping)


def test_research_search_tavily_gate_uses_research_flow_artifacts(
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

    result = _runner().run_capability(
        "research.search",
        inputs={
            "root": str(tmp_path),
            "query": "capacity research integration",
            "provider": "tavily",
            "provider_gate": "tavily_research",
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

    result = _runner().run_capability(
        "research.search",
        inputs={
            "root": str(tmp_path),
            "query": "https://example.com/exact-url",
            "provider": "tavily",
            "provider_gate": "tavily_research",
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


def test_research_search_codex_gate_uses_research_flow_artifacts(
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
            "provider": "codex",
            "provider_gate": "codex_research",
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


def test_research_promote_capability_builds_low_sensitive_proposal_summary(tmp_path):
    store = ArtifactStore(tmp_path)
    artifact = store.create_artifact(
        "run_research",
        execution_id="exec_research",
        artifact_type="research.report",
        summary="Fake research summary for capacity promotion.",
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
        "summary": "Fake research summary for capacity promotion.",
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
