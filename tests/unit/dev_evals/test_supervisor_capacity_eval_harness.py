import json

from isotope.dev_evals.cases import scenario_catalog
from isotope.dev_evals.supervisor_capacity_eval import (
    DeterministicScenarioProvider,
    main,
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
    prompt_ref = case["reviewer_prompt_ref"]
    assert prompt_ref["path"].endswith(
        "state/dev-evals/reviewer-prompts/code_search_fixture.md"
    )
    assert (tmp_path / prompt_ref["path"]).read_text().startswith(
        "You are reviewing the current Codex development work"
    )
    assert "raw_response" not in json.dumps(report)


def test_harness_runs_research_recall_case_against_seeded_report(tmp_path):
    scenario = next(
        item for item in scenario_catalog() if item.case_id == "research_recall_fixture"
    )
    provider = DeterministicScenarioProvider(
        [
            {
                "kind": "call_capability",
                "capacity_id": "research.recall",
                "arguments": {"query": "RAG_RECALL_EVAL_MARKER", "limit": 5},
                "rationale": "Need existing research report recall.",
            },
            {
                "kind": "direct_answer",
                "answer": "Recalled the stored report preview.",
                "answer_basis": {
                    "kind": "observation",
                    "capacity_ids": ["research.recall"],
                    "reason": "Research recall observation returned the marker.",
                },
                "rationale": "Observation is enough.",
            },
        ]
    )

    report = run_scenarios([scenario], root=tmp_path, provider=provider, live=False)

    assert report["status"] == "passed"
    case = report["cases"][0]
    assert case["hard_gate_passed"] is True
    assert case["steps"][0]["capacity_id"] == "research.recall"
    assert (
        case["steps"][0]["result_summary"][
            "agent_loop_research_recall_result_count"
        ]
        == 1
    )
    rendered_report = json.dumps(report)
    assert "RAG_RECALL_EVAL_MARKER" in rendered_report
    assert "raw_response" not in rendered_report
    assert "must_not_leak" not in rendered_report.lower()


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


def test_cli_uses_fresh_default_run_root_each_time(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    first_status = main(
        [
            "--deterministic-provider",
            "--case-id",
            "artifact_review_demo",
            "--json",
        ]
    )
    second_status = main(
        [
            "--deterministic-provider",
            "--case-id",
            "artifact_review_demo",
            "--json",
        ]
    )
    captured = capsys.readouterr()

    assert first_status == 0
    assert second_status == 0
    run_roots = sorted((tmp_path / ".dev-eval-runs").glob("run-*"))
    assert len(run_roots) == 2
    assert run_roots[0] != run_roots[1]
    assert all(
        (run_root / "state/dev-evals/reviewer-prompts/artifact_review_demo.md").exists()
        for run_root in run_roots
    )
    assert '"run_root": ".dev-eval-runs/run-' in captured.out
