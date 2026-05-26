import importlib

import pytest


def _catalog_module():
    return importlib.import_module("isotope.capabilities.catalog")


def _capability_class():
    return getattr(_catalog_module(), "Capability")


def _catalog_class():
    return getattr(_catalog_module(), "CapabilityCatalog")


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
    return _capability_class()(**data)


def _catalog():
    return _catalog_class()(
        capabilities=[
            _capability("zeta.diagnostic", "diagnostic"),
            _capability("artifact.review", "product_candidate"),
            _capability("external.snapshot.review", "prototype"),
            _capability("alpha.experimental", "experimental"),
        ]
    )


def _ids(entries):
    return [entry["capability_id"] for entry in entries]


def test_default_listing_only_exposes_product_candidate_and_prototype():
    entries = _catalog().list_capabilities()

    assert _ids(entries) == ["artifact.review", "external.snapshot.review"]


def test_diagnostic_capabilities_are_hidden_until_explicitly_included():
    default_entries = _catalog().list_capabilities()
    diagnostic_entries = _catalog().list_capabilities(include_diagnostics=True)

    assert "zeta.diagnostic" not in _ids(default_entries)
    assert _ids(diagnostic_entries) == [
        "artifact.review",
        "external.snapshot.review",
        "zeta.diagnostic",
    ]


def test_experimental_capabilities_require_explicit_opt_in():
    default_entries = _catalog().list_capabilities()
    experimental_entries = _catalog().list_capabilities(include_experimental=True)

    assert "alpha.experimental" not in _ids(default_entries)
    assert _ids(experimental_entries) == [
        "alpha.experimental",
        "artifact.review",
        "external.snapshot.review",
    ]


def test_listing_rejects_malformed_include_flags():
    catalog = _catalog()

    for flag_name in ("include_diagnostics", "include_experimental"):
        with pytest.raises(ValueError, match=flag_name):
            catalog.list_capabilities(**{flag_name: "yes"})


def test_shelf_filter_can_select_diagnostics_without_showing_other_shelves():
    entries = _catalog().list_capabilities(shelf="diagnostic")

    assert _ids(entries) == ["zeta.diagnostic"]


def test_experimental_shelf_filter_still_requires_explicit_opt_in():
    hidden_entries = _catalog().list_capabilities(shelf="experimental")
    visible_entries = _catalog().list_capabilities(
        shelf="experimental", include_experimental=True
    )

    assert hidden_entries == []
    assert _ids(visible_entries) == ["alpha.experimental"]


def test_listing_order_is_deterministic_by_capability_id():
    entries = _catalog().list_capabilities(
        include_diagnostics=True, include_experimental=True
    )

    assert _ids(entries) == [
        "alpha.experimental",
        "artifact.review",
        "external.snapshot.review",
        "zeta.diagnostic",
    ]


def test_default_builtins_are_small_product_candidate_set_only():
    catalog = _catalog_class().default()

    entries = catalog.list_capabilities(include_diagnostics=True, include_experimental=True)
    capability_ids = _ids(entries)

    assert capability_ids == [
        "approval.tool.runner",
        "artifact.review",
        "external.snapshot.review",
        "memory.query",
        "research.search",
        "screen.report",
        "supervisor.integration_review",
        "supervisor.request_context",
        "supervisor.worker_review",
    ]
    assert all(entry["shelf"] == "product_candidate" for entry in entries)
    assert "self.evolution.review" not in capability_ids
    assert "llm.chat" not in capability_ids
