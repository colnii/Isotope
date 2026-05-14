import json
from pathlib import Path

import pytest

from isotope.capability_catalog import Capability, CapabilityCatalog
from isotope.capability_runner import CapabilityRunner


FORBIDDEN_KEYS = {
    "api_key",
    "content",
    "full_content",
    "local_path",
    "prompt",
    "raw_content",
    "trace",
    "transcript",
}


def _capability(capability_id, shelf="product_candidate", **overrides):
    data = {
        "capability_id": capability_id,
        "title": capability_id.replace(".", " ").title(),
        "description": f"{capability_id} capability metadata.",
        "maturity": "v0.2",
        "shelf": shelf,
        "domain_tags": tuple(capability_id.split(".")),
        "input_contract": {"type": "object", "required": []},
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


def _runner(*, catalog=None):
    return CapabilityRunner(catalog=catalog or CapabilityCatalog.default())


def _walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _assert_low_sensitive(value):
    json.dumps(value)
    for mapping in _walk(value):
        assert FORBIDDEN_KEYS.isdisjoint(mapping)


def test_capability_runner_is_still_the_search_and_plan_home():
    assert CapabilityRunner.__name__ == "CapabilityRunner"


def test_search_capabilities_finds_matching_catalog_entries():
    result = _runner().search_capabilities(query="artifact")

    assert result["kind"] == "capability_search_result"
    assert result["query"] == "artifact"
    ids = [entry["capability_id"] for entry in result["capabilities"]]
    assert ids == ["artifact.review"]


def test_search_capabilities_returns_low_sensitive_metadata_only():
    result = _runner().search_capabilities(query="review")

    assert result["capabilities"]
    for entry in result["capabilities"]:
        assert set(entry).issuperset(
            {
                "capability_id",
                "title",
                "description",
                "shelf",
                "domain_tags",
                "readiness",
            }
        )
    _assert_low_sensitive(result)


def test_search_capabilities_has_no_side_effects(tmp_path):
    result = _runner().search_capabilities(query="snapshot")

    assert [entry["capability_id"] for entry in result["capabilities"]] == [
        "external.snapshot.review"
    ]
    assert not list(Path(tmp_path).rglob("*"))


def test_search_capabilities_respects_shelf_and_hidden_capability_filters():
    catalog = CapabilityCatalog(
        capabilities=[
            _capability("visible.review", "product_candidate"),
            _capability("hidden.diagnostic", "diagnostic"),
            _capability("hidden.experimental", "experimental"),
        ]
    )

    default_result = _runner(catalog=catalog).search_capabilities(query="hidden")
    diagnostic_result = _runner(catalog=catalog).search_capabilities(
        query="hidden", include_diagnostics=True
    )

    assert default_result["capabilities"] == []
    assert [entry["capability_id"] for entry in diagnostic_result["capabilities"]] == [
        "hidden.diagnostic"
    ]


def test_plan_capability_run_for_allowlisted_capability_is_launchable():
    plan = _runner().plan_capability_run("artifact.review")

    assert plan["kind"] == "capability_launch_plan"
    assert plan["capability_id"] == "artifact.review"
    assert plan["capability_title"] == "Artifact Review"
    assert plan["can_launch"] is True
    assert plan["status"] == "launchable"
    assert plan["runner_kind"] == "deterministic_demo"
    assert plan["scenario"] == "artifact-review"
    assert plan["blocking_reasons"] == []
    assert plan["output_policy"] == {
        "returns_full_content": False,
        "returns_artifact_refs": True,
        "low_sensitive_summary_only": True,
    }
    _assert_low_sensitive(plan)


def test_plan_unknown_capability_returns_controlled_unknown_plan_without_side_effects(
    tmp_path,
):
    plan = _runner().plan_capability_run("unknown.capability")

    assert plan["kind"] == "capability_launch_plan"
    assert plan["capability_id"] == "unknown.capability"
    assert plan["can_launch"] is False
    assert plan["status"] == "unknown"
    assert plan["blocking_reasons"] == ["unknown_capability"]
    assert not list(Path(tmp_path).rglob("*"))
    _assert_low_sensitive(plan)


def test_plan_provider_required_capability_reports_missing_configuration_without_provider():
    catalog = CapabilityCatalog(
        capabilities=[
            _capability(
                "llm.artifact.review",
                required_env=("ISOTOPE_TEST_PROVIDER_KEY",),
                network_required=True,
                provider="deepseek",
                model="deepseek-v4-flash",
            )
        ]
    )

    plan = _runner(catalog=catalog).plan_capability_run(
        "llm.artifact.review", env={}
    )

    assert plan["can_launch"] is False
    assert plan["status"] == "not_ready"
    assert plan["runner_kind"] == "provider_required"
    assert plan["network_required"] is True
    assert plan["provider"] == "deepseek"
    assert plan["model"] == "deepseek-v4-flash"
    assert plan["missing_env"] == ["ISOTOPE_TEST_PROVIDER_KEY"]
    assert "missing_configuration" in plan["blocking_reasons"]
    _assert_low_sensitive(plan)


@pytest.mark.parametrize("shelf", ["diagnostic", "experimental"])
def test_plan_hidden_capabilities_are_not_launchable_by_default(shelf):
    catalog = CapabilityCatalog(
        capabilities=[_capability(f"{shelf}.capability", shelf)]
    )

    plan = _runner(catalog=catalog).plan_capability_run(f"{shelf}.capability")

    assert plan["can_launch"] is False
    assert plan["status"] in {"deferred", "not_allowlisted"}
    assert plan["shelf"] == shelf
    assert plan["scenario"] is None
    assert "not_allowlisted" in plan["blocking_reasons"]
    _assert_low_sensitive(plan)
