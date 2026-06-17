from isotope.capabilities.runner import CapabilityRunner
from isotope.dev_evals.cases import scenario_catalog
from isotope.dev_evals.fixtures import prepare_fixture
from isotope.workspace.artifacts import ArtifactStore


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
            "research_recall_seeded",
        }
        assert "required_capacity_called" in scenario.required_gates
        assert "low_sensitive_report" in scenario.required_gates


def test_code_search_scenario_requires_literal_marker_input():
    scenario = next(
        item for item in scenario_catalog() if item.case_id == "code_search_fixture"
    )

    assert "ISOTOPE_DEV_EVAL_MARKER" in scenario.user_message
    assert scenario.required_input_fragments == ("ISOTOPE_DEV_EVAL_MARKER",)


def test_ast_edit_scenario_requires_universal_node_selector_input():
    scenario = next(
        item for item in scenario_catalog() if item.case_id == "code_ast_edit_fixture"
    )

    assert scenario.capability_ids == ("code.ast_edit",)
    assert scenario.fixture == "workspace_with_code"
    assert scenario.required_input_fragments == ("function_definition", "def answer")


def test_research_recall_scenario_requires_marker_input():
    scenario = next(
        item for item in scenario_catalog() if item.case_id == "research_recall_fixture"
    )

    assert "RAG_RECALL_EVAL_MARKER" in scenario.user_message
    assert scenario.fixture == "research_recall_seeded"
    assert scenario.required_input_fragments == ("RAG_RECALL_EVAL_MARKER",)


def test_research_recall_fixture_seeds_preview_only_report(tmp_path):
    state_root, _workspace = prepare_fixture(tmp_path, "research_recall_seeded")
    artifacts = ArtifactStore(state_root).list_artifacts("run_research_recall_eval")

    assert len(artifacts) == 1
    assert artifacts[0].artifact_type == "research.report"
    assert "RAG_RECALL_EVAL_MARKER" in artifacts[0].summary


def test_screen_control_approval_scenario_requires_approval_guard():
    scenario = next(
        item for item in scenario_catalog() if item.case_id == "screen_control_approval_fixture"
    )

    assert scenario.capability_ids == ("screen.control",)
    assert scenario.fixture == "screen_config_gated"
    assert "screen_control_approval_guard" in scenario.required_gates
    assert scenario.allowed_result_statuses == ("pending_user_approval",)
