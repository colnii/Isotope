import json
from typing import Any

from isotope.demo import run_demo


SCENARIO = "artifact-review"

FORBIDDEN_CONTENT_KEYS = {
    "content",
    "artifact_content",
    "full_content",
    "raw_content",
    "raw_artifact_content",
}


def _assert_no_forbidden_content_keys(value: Any) -> None:
    if isinstance(value, dict):
        forbidden = FORBIDDEN_CONTENT_KEYS.intersection(value)
        assert forbidden == set()
        for nested in value.values():
            _assert_no_forbidden_content_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_forbidden_content_keys(nested)


def test_artifact_review_flow_starts_from_existing_artifact_summary_and_ref(tmp_path):
    data = run_demo(tmp_path, scenario=SCENARIO)

    assert data["source_summary"]["ref"] == data["artifact_ref"]
    assert data["source_summary"]["summary"]
    assert "provenance" in data["source_summary"]
    assert data["source_summary"]["provenance"]["execution_id"]
    _assert_no_forbidden_content_keys(data["source_summary"])


def test_artifact_reviewer_action_uses_action_chain_and_artifact_handoff(tmp_path):
    data = run_demo(tmp_path, scenario=SCENARIO)
    event_types = data["event_types"]

    assert data["review_action_chain_ok"] is True
    assert event_types.count("action.proposed") >= 2
    assert event_types.count("action.decided") >= 2
    assert event_types.count("action.started") >= 2
    assert event_types.count("artifact.created") >= 2
    assert event_types.count("action.completed") >= 2
    assert data["review_artifact_ref"] in data["replay_artifact_refs"]
    assert data["review_artifact_ref"] in data["checkpoint_artifact_refs"]


def test_artifact_review_decision_and_artifact_keep_provenance(tmp_path):
    data = run_demo(tmp_path, scenario=SCENARIO)

    review_decision = data["review_decision"]
    review_provenance = data["review_artifact_provenance"]
    assert review_decision["status"] == "accepted"
    assert review_decision["source_ref"] == data["artifact_ref"]
    assert review_decision["basis_summary"] == data["source_summary"]["summary"]
    assert review_decision["provenance"]["source_ref"] == data["artifact_ref"]
    assert review_decision["provenance"]["review_artifact_ref"] == data["review_artifact_ref"]
    assert review_provenance["execution_id"]


def test_artifact_review_content_policy_and_http_content_route_are_active(tmp_path):
    data = run_demo(tmp_path, scenario=SCENARIO)

    assert data["content_policy_ok"] is True
    assert data["metadata_projection_ok"] is True
    assert data["controlled_retrieval_ok"] is True
    assert data["controlled_retrieval_view"] == "full"
    assert data["http_full_content_route_status"] == "active"
    _assert_no_forbidden_content_keys(data)


def test_artifact_review_replay_and_checkpoint_restore_review_summary(tmp_path):
    data = run_demo(tmp_path, scenario=SCENARIO)

    assert data["replay_ok"] is True
    assert data["checkpoint_ok"] is True
    assert data["review_summary"] in data["replay_artifact_summaries"]
    assert data["review_summary"] in data["checkpoint_artifact_summaries"]
    assert data["review_artifact_ref"] in data["checkpoint_artifact_refs"]


def test_artifact_review_projected_state_does_not_contain_raw_content(tmp_path):
    data = run_demo(tmp_path, scenario=SCENARIO)
    serialized = json.dumps(
        {
            "source_summary": data["source_summary"],
            "review_decision": data["review_decision"],
            "replay_artifacts": data["replay_artifacts"],
            "checkpoint_artifacts": data["checkpoint_artifacts"],
        },
        sort_keys=True,
    )

    assert "source artifact durable content" not in serialized
    assert "review artifact durable content" not in serialized
    _assert_no_forbidden_content_keys(data["replay_artifacts"])
    _assert_no_forbidden_content_keys(data["checkpoint_artifacts"])
