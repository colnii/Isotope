from isotope.dev_evals.reviewer_prompt import render_reviewer_prompt


def test_reviewer_prompt_contains_diff_trace_scores_and_instructions():
    prompt = render_reviewer_prompt(
        diff_summary="M src/isotope/dev_evals/gates.py",
        report={
            "suite": "supervisor_capacity_basic",
            "status": "failed",
            "cases": [
                {
                    "case_id": "code_search_fixture",
                    "hard_gates": [
                        {"gate": "required_capacity_called", "passed": False}
                    ],
                    "scores": {"capacity_choice": 1},
                    "steps": [{"capacity_id": "code.read", "status": "ok"}],
                }
            ],
        },
    )

    assert "current git diff" in prompt
    assert "supervisor_capacity_basic" in prompt
    assert "required_capacity_called" in prompt
    assert "code.read" in prompt
    assert "rerun the required eval" in prompt
    assert "report what changed" in prompt
