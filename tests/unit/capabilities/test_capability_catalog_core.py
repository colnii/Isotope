import importlib
import json

import pytest


FORBIDDEN_MANIFEST_KEYS = {
    "api_key",
    "content",
    "full_content",
    "local_path",
    "prompt",
    "raw_content",
    "trace",
    "transcript",
}


def _catalog_module():
    return importlib.import_module("isotope.capabilities.catalog")


def _capability_class():
    return getattr(_catalog_module(), "Capability")


def _catalog_class():
    return getattr(_catalog_module(), "CapabilityCatalog")


def _valid_capability(**overrides):
    data = {
        "capability_id": "artifact.review",
        "title": "Artifact Review",
        "description": "Review an artifact through summary and ResourceRef boundaries.",
        "maturity": "v0.2",
        "shelf": "product_candidate",
        "domain_tags": ("artifact", "review"),
        "input_contract": {"type": "object", "required": ["artifact_ref"]},
        "output_contract": {"type": "object", "fields": ["review_artifact_ref"]},
        "safety_boundaries": ("summary_only", "no_full_content"),
        "default_enabled": True,
        "required_env": (),
        "network_required": False,
        "provider": None,
        "model": None,
    }
    data.update(overrides)
    return _capability_class()(**data)


def _walk_mapping(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_mapping(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_mapping(child)


def test_capability_catalog_module_exists():
    module = _catalog_module()

    assert module.__name__ == "isotope.capabilities.catalog"


def test_capability_serializes_to_low_sensitive_manifest_dict():
    capability = _valid_capability()

    manifest = capability.to_manifest_dict()

    assert manifest["capability_id"] == "artifact.review"
    assert manifest["title"] == "Artifact Review"
    assert manifest["shelf"] == "product_candidate"
    assert manifest["domain_tags"] == ["artifact", "review"]
    assert manifest["default_enabled"] is True
    assert "input_contract" in manifest
    assert "output_contract" in manifest
    assert "safety_boundaries" in manifest
    json.dumps(manifest)

    for mapping in _walk_mapping(manifest):
        assert FORBIDDEN_MANIFEST_KEYS.isdisjoint(mapping)


def test_capability_manifest_nested_contracts_are_isolated_copies():
    capability = _valid_capability(
        input_contract={
            "type": "object",
            "required": ["artifact_ref"],
            "properties": {"artifact_ref": {"type": "string"}},
        }
    )

    manifest = capability.to_manifest_dict()
    manifest["input_contract"]["properties"]["artifact_ref"]["type"] = "object"

    fresh_manifest = capability.to_manifest_dict()

    assert (
        fresh_manifest["input_contract"]["properties"]["artifact_ref"]["type"]
        == "string"
    )


def test_capability_copies_nested_contracts_at_construction():
    input_contract = {
        "type": "object",
        "properties": {"artifact_ref": {"type": "string"}},
    }
    output_contract = {
        "type": "object",
        "fields": [{"name": "review_artifact_ref", "type": "string"}],
    }
    capability = _valid_capability(
        input_contract=input_contract,
        output_contract=output_contract,
    )

    input_contract["properties"]["artifact_ref"]["type"] = "object"
    output_contract["fields"][0]["type"] = "object"

    manifest = capability.to_manifest_dict()

    assert (
        manifest["input_contract"]["properties"]["artifact_ref"]["type"]
        == "string"
    )
    assert manifest["output_contract"]["fields"][0]["type"] == "string"


def test_capability_catalog_rejects_duplicate_capability_ids():
    capability = _valid_capability(capability_id="artifact.review")
    duplicate = _valid_capability(capability_id="artifact.review", title="Duplicate")

    with pytest.raises(ValueError, match="duplicate capability_id"):
        _catalog_class()(capabilities=[capability, duplicate])


def test_capability_catalog_rejects_malformed_capabilities_collection():
    with pytest.raises(ValueError, match="capabilities"):
        _catalog_class()(capabilities=object())


@pytest.mark.parametrize(
    "capability_id",
    ["", "Artifact Review", "artifact_review", "artifact/review", "artifact..review"],
)
def test_capability_rejects_malformed_stable_ids(capability_id):
    with pytest.raises(ValueError, match="capability_id"):
        _valid_capability(capability_id=capability_id)


def test_capability_rejects_unknown_shelf():
    with pytest.raises(ValueError, match="shelf"):
        _valid_capability(shelf="private_experiment")


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("provider", ""),
        ("provider", 5),
        ("model", ""),
        ("model", 5),
    ],
)
def test_capability_rejects_malformed_optional_provider_metadata(
    field_name, bad_value
):
    with pytest.raises(ValueError, match=field_name):
        _valid_capability(**{field_name: bad_value})


def test_manifest_returns_json_compatible_metadata_and_readiness_only():
    catalog = _catalog_class()(
        capabilities=[
            _valid_capability(capability_id="artifact.review"),
            _valid_capability(
                capability_id="external.snapshot.review",
                title="External Snapshot Review",
                shelf="prototype",
            ),
        ]
    )

    manifest = catalog.get_manifest(env={})

    assert manifest["kind"] == "capability_manifest"
    assert [entry["capability_id"] for entry in manifest["capabilities"]] == [
        "artifact.review",
        "external.snapshot.review",
    ]
    assert all("readiness" in entry for entry in manifest["capabilities"])
    json.dumps(manifest)

    for mapping in _walk_mapping(manifest):
        assert FORBIDDEN_MANIFEST_KEYS.isdisjoint(mapping)


def test_capability_status_reports_missing_configuration_without_provider_setup():
    catalog = _catalog_class()(
        capabilities=[
            _valid_capability(
                capability_id="llm.artifact.review",
                title="LLM Artifact Review",
                required_env=("ISOTOPE_TEST_REQUIRED_KEY",),
                network_required=True,
                provider="test-provider",
                model="test-model",
            )
        ]
    )

    status = catalog.get_capability_status("llm.artifact.review", env={})

    assert status == {
        "capability_id": "llm.artifact.review",
        "default_enabled": True,
        "ready": False,
        "status": "missing_configuration",
        "missing_env": ["ISOTOPE_TEST_REQUIRED_KEY"],
        "network_required": True,
        "provider": "test-provider",
        "model": "test-model",
    }


def test_capability_status_rejects_malformed_env_mapping():
    catalog = _catalog_class()(
        capabilities=[_valid_capability(required_env=("ISOTOPE_TEST_REQUIRED_KEY",))]
    )

    with pytest.raises(ValueError, match="env"):
        catalog.get_capability_status("artifact.review", env=[])


def test_module_level_default_manifest_uses_same_low_sensitive_contract():
    module = _catalog_module()

    manifest = module.get_manifest(env={})

    assert manifest["kind"] == "capability_manifest"
    assert isinstance(manifest["capabilities"], list)
    json.dumps(manifest)
    for mapping in _walk_mapping(manifest):
        assert FORBIDDEN_MANIFEST_KEYS.isdisjoint(mapping)


def test_default_catalog_registers_supervisor_request_context_capability():
    catalog = _catalog_class().default()

    capability = {
        entry["capability_id"]: entry
        for entry in catalog.list_capabilities()
    }["supervisor.request_context"]

    assert capability["shelf"] == "product_candidate"
    assert capability["input_contract"]["required"] == ["state_root", "cwd", "query"]
    assert capability["input_contract"]["properties"]["max_results"]["type"] == "integer"
    assert "workspace_read_only" in capability["safety_boundaries"]
    assert "writes_existing_supervisor_context_store" in capability["safety_boundaries"]
