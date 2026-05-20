from __future__ import annotations

import pytest

from isotope.features.supervisor.merge_dispatch import (
    build_merge_dispatch_launch_spec,
)


def test_merge_dispatch_builds_controlled_launch_session_spec():
    payload = _integration_review_payload()

    spec = build_merge_dispatch_launch_spec(
        payload,
        cwd="/repo",
        target_name="supervisor-merge-dispatch",
    )

    assert spec is not None
    assert spec["kind"] == "launch_session"
    assert spec["target_name"] == "supervisor-merge-dispatch"
    assert spec["cwd"] == "/repo"
    assert spec["source"] == "integration_review"
    assert spec["reason"] == "ready_to_integrate workers require merge dispatch"
    assert spec["review"]["requires_human_review"] is True
    assert spec["integration_summary"] == {
        "base_ref": "main",
        "ready_to_integrate": 1,
    }
    assert spec["prompt"].startswith("WORK ORDER\n")
    assert "source: supervisor integration-review payload" in spec["prompt"]
    assert "ready-one / managed-ready" in spec["prompt"]
    assert "cherry-pick" in spec["prompt"]


def test_merge_dispatch_does_not_generate_launch_spec_without_ready_workers():
    payload = _integration_review_payload()
    payload["groups"]["ready_to_integrate"] = []
    payload["summary"]["ready_to_integrate"] = 0

    assert build_merge_dispatch_launch_spec(payload, cwd="/repo") is None


def test_merge_dispatch_requires_base_cwd_when_launching():
    with pytest.raises(ValueError, match="cwd is required"):
        build_merge_dispatch_launch_spec(_integration_review_payload(), cwd=" ")


def _integration_review_payload() -> dict[str, object]:
    return {
        "status": "ok",
        "base_ref": "main",
        "summary": {
            "total": 1,
            "ready_to_integrate": 1,
            "already_integrated": 0,
            "needs_review": 0,
            "conflict_risk": 0,
        },
        "groups": {
            "ready_to_integrate": [
                {
                    "record_id": "managed-ready",
                    "name": "ready-one",
                    "cwd": "/repo/.worktrees/supervisor/ready-12345678",
                    "branch": "supervisor/ready-12345678",
                    "worker_commit": "ready111",
                    "base_ref": "main",
                    "reason": "worker 已完成、分支干净、main 尚未包含且未检测到 merge conflict。",
                    "dirty": False,
                    "merge_conflict": False,
                }
            ],
            "conflict_risk": [],
            "needs_review": [],
            "already_integrated": [],
        },
    }
