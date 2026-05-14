import importlib
import json
from pathlib import Path

import pytest

from isotope_kernel.capability_catalog import Capability, CapabilityCatalog


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
    return importlib.import_module("isotope_kernel.capability_runner")


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

    assert module.__name__ == "isotope_kernel.capability_runner"


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
