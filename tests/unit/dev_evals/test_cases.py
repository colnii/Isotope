from isotope.capabilities.runner import CapabilityRunner
from isotope.dev_evals.cases import scenario_catalog


def test_scenario_catalog_covers_every_registered_capability():
    registered = {
        item["capability_id"]
        for item in CapabilityRunner().list_capabilities(
            include_diagnostics=True,
            include_experimental=True,
        )
    }
    covered = {
        capability_id
        for scenario in scenario_catalog()
        for capability_id in scenario.capability_ids
    }

    assert registered - covered == set()


def test_scenarios_have_mechanical_gate_contracts():
    for scenario in scenario_catalog():
        assert scenario.case_id
        assert scenario.user_message.strip()
        assert scenario.capability_ids
        assert scenario.fixture in {
            "empty_state",
            "workspace_with_code",
            "workspace_with_diff",
            "memory_seeded",
            "artifact_seeded",
            "mcp_configured",
            "screen_config_gated",
            "provider_config_gated",
        }
        assert "required_capacity_called" in scenario.required_gates
        assert "low_sensitive_report" in scenario.required_gates
