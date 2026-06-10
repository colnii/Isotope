import json

from isotope.dev_evals.cases import scenario_catalog
from isotope.dev_evals.supervisor_capacity_eval import (
    DeterministicScenarioProvider,
    run_scenarios,
)


def test_harness_runs_code_search_case_through_conversation_loop(tmp_path):
    scenario = next(
        item for item in scenario_catalog() if item.case_id == "code_search_fixture"
    )
    provider = DeterministicScenarioProvider(
        [
            {
                "kind": "call_capability",
                "capacity_id": "code.search",
                "arguments": {
                    "query": "ISOTOPE_DEV_EVAL_MARKER",
                    "include_paths": ["src"],
                    "max_results": 5,
                },
                "rationale": "Need code search.",
            },
            {
                "kind": "direct_answer",
                "answer": "Found the marker via code.search.",
                "answer_basis": {
                    "kind": "observation",
                    "capacity_ids": ["code.search"],
                    "reason": "Search observation returned the fixture marker.",
                },
                "rationale": "Observation is enough.",
            },
        ]
    )

    report = run_scenarios([scenario], root=tmp_path, provider=provider, live=False)

    assert report["status"] == "passed"
    case = report["cases"][0]
    assert case["steps"][0]["capacity_id"] == "code.search"
    assert case["hard_gate_passed"] is True
    assert "raw_response" not in json.dumps(report)


def test_harness_fails_when_provider_chooses_wrong_capacity(tmp_path):
    scenario = next(
        item for item in scenario_catalog() if item.case_id == "code_search_fixture"
    )
    provider = DeterministicScenarioProvider(
        [
            {
                "kind": "call_capability",
                "capacity_id": "code.read",
                "arguments": {"path": "src/app.py"},
                "rationale": "Wrong capability for this case.",
            },
            {
                "kind": "direct_answer",
                "answer": "Read the file.",
                "answer_basis": {
                    "kind": "observation",
                    "capacity_ids": ["code.read"],
                    "reason": "Read observation exists.",
                },
                "rationale": "Stop.",
            },
        ]
    )

    report = run_scenarios([scenario], root=tmp_path, provider=provider, live=False)

    assert report["status"] == "failed"
    assert report["cases"][0]["hard_gates"][0]["details"][
        "missing_capacity_ids"
    ] == ["code.search"]
