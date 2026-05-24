from __future__ import annotations

import pytest

from isotope.agents.loop.loop_engine import LoopEngine, LoopInterrupted


def test_loop_engine_runs_registered_step_handler_and_refreshes_control():
    controls = [
        {
            "run_id": "run_001",
            "phase": "ready",
            "status": "running",
            "next_actions": ["collect_evidence"],
        },
        {
            "run_id": "run_001",
            "phase": "completed",
            "status": "completed",
            "next_actions": [],
        },
    ]
    calls: list[dict[str, object]] = []

    def get_control(run_id: str) -> dict[str, object]:
        assert run_id == "run_001"
        return controls.pop(0)

    def collect_evidence(context):
        calls.append(
            {
                "run_id": context.run_id,
                "step": context.step,
                "phase": context.control["phase"],
                "request": context.request,
            }
        )
        return {"status": "completed", "artifact_id": "artifact_001"}

    engine = LoopEngine(
        get_control=get_control,
        step_handlers={"collect_evidence": collect_evidence},
    )

    result = engine.run_step(
        "run_001",
        {
            "step": "collect_evidence",
            "query": "recent events",
        },
    )

    assert result == {
        "step": "collect_evidence",
        "status": "completed",
        "action_result": {"status": "completed", "artifact_id": "artifact_001"},
        "control": {
            "run_id": "run_001",
            "phase": "completed",
            "status": "completed",
            "next_actions": [],
        },
    }
    assert calls == [
        {
            "run_id": "run_001",
            "step": "collect_evidence",
            "phase": "ready",
            "request": {
                "step": "collect_evidence",
                "query": "recent events",
            },
        }
    ]


def test_loop_engine_interrupt_policy_stops_before_step_handler():
    calls: list[str] = []

    def get_control(_run_id: str) -> dict[str, object]:
        return {
            "run_id": "run_001",
            "phase": "ready",
            "status": "running",
            "next_actions": ["collect_evidence"],
        }

    def collect_evidence(_context):
        calls.append("called")
        return {"status": "completed"}

    def interrupt_policy(context):
        assert context.step == "collect_evidence"
        return "user_paused"

    engine = LoopEngine(
        get_control=get_control,
        step_handlers={"collect_evidence": collect_evidence},
        interrupt_policy=interrupt_policy,
    )

    with pytest.raises(LoopInterrupted) as exc_info:
        engine.run_step("run_001", {"step": "collect_evidence"})

    assert exc_info.value.reason == "user_paused"
    assert exc_info.value.control["phase"] == "ready"
    assert calls == []
