from isotope.dev_evals.gates import (
    evaluate_required_capacity_called,
    low_sensitive_report_passed,
)
from isotope.dev_evals.models import CapabilityScenario
from isotope.dev_evals.reporting import build_case_report, sanitize_value


def test_required_capacity_gate_fails_when_expected_capacity_missing():
    scenario = CapabilityScenario(
        case_id="code_search_fixture",
        capability_ids=("code.search",),
        user_message="Find marker.",
        fixture="workspace_with_code",
    )
    steps = [{"capacity_id": "code.read", "status": "ok"}]

    gate = evaluate_required_capacity_called(scenario, steps)

    assert gate["gate"] == "required_capacity_called"
    assert gate["passed"] is False
    assert gate["details"]["missing_capacity_ids"] == ["code.search"]


def test_low_sensitive_sanitizer_redacts_raw_payloads():
    value = {
        "raw_response": "SHOULD_NOT_LEAK",
        "token": "SECRET",
        "safe": {"capacity_id": "code.search"},
        "items": [{"raw_prompt": "PROMPT_SHOULD_NOT_LEAK"}],
    }

    sanitized = sanitize_value(value)

    assert "SHOULD_NOT_LEAK" not in repr(sanitized)
    assert "SECRET" not in repr(sanitized)
    assert sanitized["safe"] == {"capacity_id": "code.search"}
    assert sanitized["items"] == [{"raw_prompt": "[redacted]"}]


def test_case_report_status_follows_hard_gates():
    scenario = CapabilityScenario(
        case_id="code_search_fixture",
        capability_ids=("code.search",),
        user_message="Find marker.",
        fixture="workspace_with_code",
    )
    report = build_case_report(
        scenario,
        steps=[{"capacity_id": "code.read", "status": "ok"}],
        final_answer="No marker.",
    )

    assert report["status"] == "failed"
    assert report["hard_gate_passed"] is False


def test_case_report_fails_when_required_input_fragment_is_missing():
    scenario = CapabilityScenario(
        case_id="code_search_fixture",
        capability_ids=("code.search",),
        user_message="Find the literal marker ISOTOPE_DEV_EVAL_MARKER.",
        fixture="workspace_with_code",
        required_input_fragments=("ISOTOPE_DEV_EVAL_MARKER",),
    )

    report = build_case_report(
        scenario,
        steps=[
            {
                "capacity_id": "code.search",
                "status": "ok",
                "input_summary": {"query": "fixture marker"},
            }
        ],
        final_answer="No marker.",
    )

    assert report["status"] == "failed"
    gate = next(
        item for item in report["hard_gates"] if item["gate"] == "required_input_fragments"
    )
    assert gate["details"]["missing_fragments"] == ["ISOTOPE_DEV_EVAL_MARKER"]
