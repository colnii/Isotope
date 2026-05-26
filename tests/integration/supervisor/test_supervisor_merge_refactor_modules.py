from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from isotope.features.supervisor.merge.merge_dispatch import (
    build_merge_dispatch_payload,
)
from isotope.features.supervisor.merge.merge_promotion import (
    check_main_promotion_preconditions,
    merge_promotion_decision_intent,
)
from isotope.features.supervisor.merge.merge_repair import (
    blocked_merge_worker_cwd,
    merge_dispatch_conflict_repair_prompt,
)


def test_merge_dispatch_payload_builds_ready_launch_spec_without_runner_private_logic():
    review_payload = {
        "base_ref": "main",
        "summary": {"ready_to_integrate": 1},
        "safety": {"auto_merge": False},
        "groups": {
            "ready_to_integrate": [
                {
                    "record_id": "managed-ready",
                    "name": "ready-worker",
                    "branch": "supervisor/ready-worker",
                    "worker_commit": "ready123",
                }
            ]
        },
    }

    payload = build_merge_dispatch_payload(
        review_payload,
        cwd=Path("/repo"),
        running_worker=None,
        managed_worker_reference=lambda record: {"record_id": record.record_id},
    )

    assert payload is not None
    assert payload["status"] == "ready_to_launch"
    assert payload["launch_spec"]["target_name"] == "supervisor-merge-dispatch"
    assert payload["integration_review"]["summary"] == {"ready_to_integrate": 1}


def test_blocked_merge_repair_helpers_keep_repair_in_merge_worker_worktree(tmp_path):
    cwd = tmp_path / "merge-worker"
    cwd.mkdir()
    item = {
        "name": "supervisor-merge-dispatch",
        "record_id": "managed-merge",
        "cwd": str(cwd),
        "branch": "supervisor/supervisor-merge-dispatch",
        "worker_commit": "merge123",
        "supervisor_protocol": {
            "summary": "cherry-pick 时出现 conflict",
            "next": "继续处理当前 cherry-pick",
        },
    }

    assert blocked_merge_worker_cwd(item, record=None) == cwd
    prompt = merge_dispatch_conflict_repair_prompt(item=item, cwd=cwd)

    assert f"cwd: {cwd}" in prompt
    assert "git status" in prompt
    assert "cherry-pick --continue" in prompt
    assert "SUPERVISOR_STATUS" in prompt


def test_merge_promotion_helpers_classify_decisions_and_check_clean_main(tmp_path):
    assert merge_promotion_decision_intent({"answer": "请修复后 retry"}) == "repair"
    assert merge_promotion_decision_intent({"answer": "放弃这次合并"}) == "abandon"
    assert merge_promotion_decision_intent({"answer": "再试一次"}) == "retry"

    commands: list[list[str]] = []

    def fake_run(
        command: list[str],
        **_: Any,
    ) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        if command[-2:] == ["--abbrev-ref", "HEAD"]:
            return subprocess.CompletedProcess(command, 0, "main\n", "")
        if command[-2:] == ["status", "--short"]:
            return subprocess.CompletedProcess(command, 0, "", "")
        raise AssertionError(command)

    assert check_main_promotion_preconditions(tmp_path, run=fake_run) is None
    assert commands == [
        ["git", "-C", str(tmp_path), "rev-parse", "--abbrev-ref", "HEAD"],
        ["git", "-C", str(tmp_path), "status", "--short"],
    ]
