import isotope.demo as demo
from isotope import demo_artifact_review_scenarios


def test_demo_facade_reexports_artifact_review_scenario_runner():
    assert (
        demo._run_artifact_review_spike
        is demo_artifact_review_scenarios._run_artifact_review_spike
    )
