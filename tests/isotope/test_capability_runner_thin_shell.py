import importlib
import json
from pathlib import Path

import pytest

from isotope.capabilities.catalog import Capability, CapabilityCatalog


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
    assert description["input_contract"]["required"] == ["codex_home", "cwd", "query"]
    assert "workspace_read_only" in description["safety_boundaries"]
    assert "writes_existing_supervisor_context_store" in description["safety_boundaries"]


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


def test_request_context_plan_stops_when_required_inputs_are_missing():
    plan = _runner().plan_capability_run(
        "supervisor.request_context",
        inputs={"cwd": "/tmp/project"},
    )

    assert plan["can_launch"] is False
    assert plan["status"] == "missing_inputs"
    assert plan["runner_kind"] == "deterministic_readonly"
    assert plan["missing_inputs"] == ["codex_home", "query"]
    assert plan["scenario"] is None


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("codex_home", 123),
        ("cwd", ["workspace"]),
        ("query", {"text": "request_context"}),
    ],
)
def test_request_context_plan_rejects_non_string_required_inputs(field_name, bad_value):
    inputs = {
        "codex_home": "/tmp/codex-home",
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
