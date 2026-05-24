from __future__ import annotations

from typing import Any

import pytest

import isotope.demo as demo
import isotope.runtime.in_process as server


def _submit_pending_approval(tmp_path):
    api = server.InProcessServer(tmp_path)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="request approval before writing")
    result = api.submit_tool_request(
        run["run_id"],
        tool="write_artifact_tool",
        text="hello",
        requires_approval=True,
    )
    approval = result["run_state"].approvals
    assert len(approval) == 1
    approval_id = next(iter(approval))
    return api, run["run_id"], approval_id, result


def _approved_body(**overrides):
    body = {
        "resolution": "approved",
        "reason": "operator approved deterministic artifact write",
        "resolver": "test_operator",
    }
    body.update(overrides)
    return body


def _denied_body(**overrides):
    body = {
        "resolution": "denied",
        "reason": "operator denied deterministic artifact write",
        "resolver": "test_operator",
    }
    body.update(overrides)
    return body


def _assert_no_internal_repr(value: Any) -> None:
    if isinstance(value, str):
        assert "object at 0x" not in value
        assert "PolicyDecision(" not in value
        assert "ActionProposal(" not in value
        assert "RunState(" not in value
    elif isinstance(value, dict):
        for nested in value.values():
            _assert_no_internal_repr(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_internal_repr(nested)


def test_get_pending_approvals_returns_projected_summary_without_event_side_effects(tmp_path):
    api, run_id, approval_id, result = _submit_pending_approval(tmp_path)
    before_events = list(api.get_events(run_id))

    approvals = api.get_pending_approvals(run_id)

    assert approvals == [
        {
            "approval_id": approval_id,
            "run_id": run_id,
            "proposal_id": result["decision"].proposal_id,
            "decision_id": result["decision"].decision_id,
            "status": "pending",
            "reason_codes": ["approval_required"],
            "requested_action_summary": {"action_type": "call_tool"},
        }
    ]
    assert api.get_events(run_id) == before_events
    _assert_no_internal_repr(approvals)


def test_get_approval_returns_copy_of_projected_summary(tmp_path):
    api, run_id, approval_id, _result = _submit_pending_approval(tmp_path)

    approval = api.get_approval(run_id, approval_id)
    approval["status"] = "mutated"

    fresh = api.get_approval(run_id, approval_id)
    assert fresh["status"] == "pending"


@pytest.mark.parametrize("body, expected_status", [(_approved_body(), "approved"), (_denied_body(), "denied")])
def test_get_approval_reads_resolved_approval_status(tmp_path, body, expected_status):
    api, run_id, approval_id, _result = _submit_pending_approval(tmp_path)

    api.resolve_approval(approval_id, body)

    assert api.get_pending_approvals(run_id) == []
    approval = api.get_approval(run_id, approval_id)
    assert approval["status"] == expected_status
    assert approval["resolution"] == expected_status
    assert approval["reason"] == body["reason"]
    assert approval["resolver"] == body["resolver"]


def test_approval_lookup_unknown_run_and_approval_are_controlled_errors(tmp_path):
    api, run_id, _approval_id, _result = _submit_pending_approval(tmp_path)

    with pytest.raises(ValueError, match="unknown run_id"):
        api.get_pending_approvals("run_missing")
    with pytest.raises(ValueError, match="unknown approval"):
        api.get_approval(run_id, "approval_missing")


def test_approval_lookup_helper_does_not_require_public_event_scan(tmp_path, monkeypatch):
    api, run_id, approval_id, _result = _submit_pending_approval(tmp_path)

    def fail_public_event_scan(*args, **kwargs):
        raise AssertionError("approval lookup helper must not require public get_events scan")

    monkeypatch.setattr(api, "get_events", fail_public_event_scan)

    assert api.get_pending_approvals(run_id)[0]["approval_id"] == approval_id
    assert api.get_approval(run_id, approval_id)["status"] == "pending"


def test_approval_tool_runner_demo_uses_lookup_helper_not_event_scan(tmp_path, monkeypatch):
    def fail_event_scan(*args, **kwargs):
        raise AssertionError("approval-tool-runner demo should not scan events for approval_id")

    monkeypatch.setattr(demo, "_latest_approval_id", fail_event_scan, raising=False)

    result = demo._run_approval_tool_runner_spike(tmp_path)

    assert result["approval_tool_runner_ok"] is True
    assert "approval_id discovery currently scans canonical events" not in result["api_friction"]

