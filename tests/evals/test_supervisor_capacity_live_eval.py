import os

import pytest

from isotope.dev_evals.supervisor_capacity_eval import run_live_suite
from isotope.llm.provider import resolve_llm_chat_provider


@pytest.mark.skipif(
    os.environ.get("ISOTOPE_RUN_LIVE_SUPERVISOR_EVAL") != "1",
    reason="live Supervisor capacity eval is opt-in",
)
def test_live_supervisor_capacity_basic_eval_records_real_provider_result(tmp_path):
    resolution = resolve_llm_chat_provider()
    report = run_live_suite(root=tmp_path, case_id="code_search_fixture", case_limit=1)

    if resolution.provider is None:
        assert report["status"] == "blocked"
        assert report["reason_code"] == resolution.reason_code
        assert report["deterministic_fallback"]["status"] == "passed"
        assert "scenario_catalog_covered" in report["deterministic_fallback"]["checks"]
    else:
        assert report["kind"] == "supervisor_capacity_dev_eval_report"
        assert report["suite"] == "supervisor_capacity_basic"
        assert report["cases"]
        assert "raw_response" not in repr(report)
