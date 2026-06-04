# Supervisor Worker Lifecycle Decision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a small programmatic lifecycle decision layer so Supervisor can choose deterministic worker follow-up actions before asking the LLM.

**Architecture:** Add a pure decision module under `src/isotope/features/supervisor/lifecycle/` that reads existing `worker-review`, `integration-review`, `merge_dispatch`, and cleanup payload shapes. First expose its result in supervisor loop payload without behavior changes, then route deterministic merge dispatch through the existing execution helpers.

**Tech Stack:** Python 3.13, pytest, existing Supervisor CLI and managed Codex worker modules.

---

## File Structure

- Create `src/isotope/features/supervisor/lifecycle/__init__.py`: package exports for lifecycle helpers.
- Create `src/isotope/features/supervisor/lifecycle/decision.py`: pure decision builder; no subprocess, git, filesystem, or registry writes.
- Create `tests/unit/features/supervisor/test_worker_lifecycle_decision.py`: focused unit tests for decision output.
- Modify `src/isotope/features/supervisor/commands/supervise/planning.py`: attach `worker_lifecycle_decision` to payload after existing `merge_dispatch` planning.
- Modify `src/isotope/features/supervisor/commands/supervise/execution.py`: use lifecycle decision for merge dispatch execution while keeping current flags and helpers.
- Modify `tests/integration/supervisor/test_supervisor_merge_dispatch_loop.py`: assert loop payload exposes lifecycle decision and still dispatches merge workers through existing helpers.
- Modify `tests/integration/supervisor/test_supervisor_auto_loop_e2e.py`: assert the closed-loop path shows the lifecycle decision before merge dispatch execution.

## Task 1: Pure Decision Module

**Files:**
- Create: `src/isotope/features/supervisor/lifecycle/__init__.py`
- Create: `src/isotope/features/supervisor/lifecycle/decision.py`
- Test: `tests/unit/features/supervisor/test_worker_lifecycle_decision.py`

- [ ] **Step 1: Write failing tests for deterministic decisions**

Create `tests/unit/features/supervisor/test_worker_lifecycle_decision.py`:

```python
from __future__ import annotations

from isotope.features.supervisor.lifecycle.decision import (
    build_worker_lifecycle_decision,
)


def test_lifecycle_decision_dispatches_merge_for_ready_workers() -> None:
    decision = build_worker_lifecycle_decision(
        integration_review=_integration_review(ready=2),
        merge_dispatch={"status": "ready_to_launch", "launch_spec": {"target_name": "supervisor-merge-dispatch"}},
    )

    assert decision["kind"] == "worker_lifecycle_decision"
    assert decision["action"] == "dispatch_merge"
    assert decision["source"] == "integration_review"
    assert decision["reason"] == "ready_to_integrate workers require merge dispatch"
    assert decision["summary"]["ready_to_integrate"] == 2
    assert decision["summary"]["merge_dispatch_status"] == "ready_to_launch"


def test_lifecycle_decision_monitors_existing_merge_worker() -> None:
    decision = build_worker_lifecycle_decision(
        integration_review=_integration_review(ready=1),
        merge_dispatch={
            "status": "worker_already_running",
            "running_worker": {"name": "supervisor-merge-dispatch"},
        },
    )

    assert decision["action"] == "monitor"
    assert decision["reason"] == "merge worker already running"
    assert decision["summary"]["running_worker"]["name"] == "supervisor-merge-dispatch"


def test_lifecycle_decision_archives_when_workers_are_integrated() -> None:
    decision = build_worker_lifecycle_decision(
        integration_review=_integration_review(already_integrated=2),
        cleanup_candidates=[{"kind": "managed_worker", "record_id": "managed-a"}],
    )

    assert decision["action"] == "archive_integrated"
    assert decision["source"] == "integration_review"
    assert decision["reason"] == "integrated workers can be archived"
    assert decision["summary"]["already_integrated"] == 2
    assert decision["summary"]["cleanup_candidates"] == 1


def test_lifecycle_decision_needs_human_for_conflicts() -> None:
    decision = build_worker_lifecycle_decision(
        integration_review=_integration_review(conflict=1, needs_review=1),
    )

    assert decision["action"] == "needs_human"
    assert decision["source"] == "integration_review"
    assert decision["reason"] == "integration review has conflict or review-required workers"
    assert decision["summary"]["conflict_risk"] == 1
    assert decision["summary"]["needs_review"] == 1


def test_lifecycle_decision_monitors_empty_review() -> None:
    decision = build_worker_lifecycle_decision()

    assert decision["action"] == "monitor"
    assert decision["source"] == "worker_review"
    assert decision["reason"] == "no lifecycle-ready worker evidence"


def _integration_review(
    *,
    ready: int = 0,
    conflict: int = 0,
    needs_review: int = 0,
    already_integrated: int = 0,
) -> dict[str, object]:
    return {
        "summary": {
            "ready_to_integrate": ready,
            "conflict_risk": conflict,
            "needs_review": needs_review,
            "already_integrated": already_integrated,
        },
        "groups": {
            "ready_to_integrate": [{"record_id": f"ready-{index}"} for index in range(ready)],
            "conflict_risk": [{"record_id": f"conflict-{index}"} for index in range(conflict)],
            "needs_review": [{"record_id": f"review-{index}"} for index in range(needs_review)],
            "already_integrated": [{"record_id": f"done-{index}"} for index in range(already_integrated)],
        },
    }
```

- [ ] **Step 2: Run tests and verify they fail because the module is missing**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/features/supervisor/test_worker_lifecycle_decision.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'isotope.features.supervisor.lifecycle'`.

- [ ] **Step 3: Implement the pure decision module**

Create `src/isotope/features/supervisor/lifecycle/__init__.py`:

```python
"""Programmatic Supervisor worker lifecycle decisions."""

from .decision import build_worker_lifecycle_decision

__all__ = ["build_worker_lifecycle_decision"]
```

Create `src/isotope/features/supervisor/lifecycle/decision.py`:

```python
"""Pure worker lifecycle decisions for Supervisor loop planning."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def build_worker_lifecycle_decision(
    *,
    worker_reviews: Mapping[str, Any] | None = None,
    integration_review: Mapping[str, Any] | None = None,
    merge_dispatch: Mapping[str, Any] | None = None,
    cleanup_candidates: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    integration_summary = _integration_summary(integration_review)
    cleanup_count = len(cleanup_candidates or [])
    summary = {
        **integration_summary,
        "cleanup_candidates": cleanup_count,
    }
    if merge_dispatch is not None:
        status = _text(merge_dispatch.get("status"))
        summary["merge_dispatch_status"] = status
        running_worker = merge_dispatch.get("running_worker")
        if isinstance(running_worker, Mapping):
            summary["running_worker"] = dict(running_worker)
        if status == "worker_already_running":
            return _decision(
                action="monitor",
                reason="merge worker already running",
                source="integration_review",
                summary=summary,
            )
    if integration_summary["conflict_risk"] or integration_summary["needs_review"]:
        return _decision(
            action="needs_human",
            reason="integration review has conflict or review-required workers",
            source="integration_review",
            summary=summary,
        )
    if integration_summary["ready_to_integrate"] and merge_dispatch is not None:
        return _decision(
            action="dispatch_merge",
            reason="ready_to_integrate workers require merge dispatch",
            source="integration_review",
            summary=summary,
        )
    if integration_summary["already_integrated"] and cleanup_count:
        return _decision(
            action="archive_integrated",
            reason="integrated workers can be archived",
            source="integration_review",
            summary=summary,
        )
    return _decision(
        action="monitor",
        reason="no lifecycle-ready worker evidence",
        source="worker_review",
        summary=summary,
    )


def _decision(
    *,
    action: str,
    reason: str,
    source: str,
    summary: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "kind": "worker_lifecycle_decision",
        "action": action,
        "reason": reason,
        "source": source,
        "summary": dict(summary),
        "execution": None,
    }


def _integration_summary(payload: Mapping[str, Any] | None) -> dict[str, int]:
    summary = payload.get("summary") if isinstance(payload, Mapping) else None
    if not isinstance(summary, Mapping):
        return {
            "ready_to_integrate": 0,
            "conflict_risk": 0,
            "needs_review": 0,
            "already_integrated": 0,
        }
    return {
        "ready_to_integrate": _non_negative_int(summary.get("ready_to_integrate")),
        "conflict_risk": _non_negative_int(summary.get("conflict_risk")),
        "needs_review": _non_negative_int(summary.get("needs_review")),
        "already_integrated": _non_negative_int(summary.get("already_integrated")),
    }


def _non_negative_int(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""
```

- [ ] **Step 4: Run unit tests and verify they pass**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/features/supervisor/test_worker_lifecycle_decision.py -q
```

Expected: `5 passed`.

- [ ] **Step 5: Commit Task 1**

Run:

```bash
git add src/isotope/features/supervisor/lifecycle tests/unit/features/supervisor/test_worker_lifecycle_decision.py
git commit -m "feat(supervisor): add worker lifecycle decisions"
```

## Task 2: Expose Decision In Supervisor Payload

**Files:**
- Modify: `src/isotope/features/supervisor/commands/supervise/planning.py`
- Test: `tests/integration/supervisor/test_supervisor_merge_dispatch_loop.py`
- Test: `tests/integration/supervisor/test_supervisor_auto_loop_e2e.py`

- [ ] **Step 1: Write failing integration assertions**

In `tests/integration/supervisor/test_supervisor_merge_dispatch_loop.py`, add these assertions after the existing `merge_dispatch` assertion in `test_supervisor_loop_dispatches_merge_worker_for_ready_integration`:

```python
    assert payload["worker_lifecycle_decision"]["action"] == "dispatch_merge"
    assert payload["worker_lifecycle_decision"]["source"] == "integration_review"
    assert payload["worker_lifecycle_decision"]["summary"]["ready_to_integrate"] == 1
```

In `tests/integration/supervisor/test_supervisor_auto_loop_e2e.py`, add these assertions after the second payload `merge_dispatch` summary assertion in `test_supervisor_loop_replenishes_done_workers_and_dispatches_merge_e2e`:

```python
    assert second_payload["worker_lifecycle_decision"]["action"] == "dispatch_merge"
    assert second_payload["worker_lifecycle_decision"]["summary"]["ready_to_integrate"] == 2
```

- [ ] **Step 2: Run tests and verify they fail because payload key is missing**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/integration/supervisor/test_supervisor_merge_dispatch_loop.py::test_supervisor_loop_dispatches_merge_worker_for_ready_integration \
  tests/integration/supervisor/test_supervisor_auto_loop_e2e.py::test_supervisor_loop_replenishes_done_workers_and_dispatches_merge_e2e -q
```

Expected: FAIL with `KeyError: 'worker_lifecycle_decision'`.

- [ ] **Step 3: Attach decision in planning payload**

Modify `src/isotope/features/supervisor/commands/supervise/planning.py`.

Add import near the top:

```python
from isotope.features.supervisor.lifecycle import build_worker_lifecycle_decision
```

After the existing `if merge_dispatch is not None: payload["merge_dispatch"] = merge_dispatch` block, add:

```python
    lifecycle_decision = build_worker_lifecycle_decision(
        worker_reviews=worker_reviews,
        integration_review=(
            merge_dispatch.get("integration_review")
            if isinstance(merge_dispatch, dict)
            else None
        ),
        merge_dispatch=merge_dispatch,
    )
    payload["worker_lifecycle_decision"] = lifecycle_decision
```

- [ ] **Step 4: Run targeted integration tests and verify they pass**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/integration/supervisor/test_supervisor_merge_dispatch_loop.py::test_supervisor_loop_dispatches_merge_worker_for_ready_integration \
  tests/integration/supervisor/test_supervisor_auto_loop_e2e.py::test_supervisor_loop_replenishes_done_workers_and_dispatches_merge_e2e -q
```

Expected: `2 passed`.

- [ ] **Step 5: Run regression set**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/features/supervisor/test_worker_lifecycle_decision.py \
  tests/integration/supervisor/test_supervisor_merge_dispatch_loop.py \
  tests/integration/supervisor/test_supervisor_auto_loop_e2e.py -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit Task 2**

Run:

```bash
git add src/isotope/features/supervisor/commands/supervise/planning.py \
  tests/integration/supervisor/test_supervisor_merge_dispatch_loop.py \
  tests/integration/supervisor/test_supervisor_auto_loop_e2e.py
git commit -m "feat(supervisor): expose worker lifecycle decisions"
```

## Task 3: Use Decision For Merge Dispatch Execution

**Files:**
- Modify: `src/isotope/features/supervisor/commands/supervise/execution.py`
- Test: `tests/integration/supervisor/test_supervisor_merge_dispatch_loop.py`

- [ ] **Step 1: Write failing assertion that execution records decision source**

In `tests/integration/supervisor/test_supervisor_merge_dispatch_loop.py`, inside `test_supervisor_loop_dispatches_merge_worker_for_ready_integration`, add after the existing executed assertions:

```python
    assert payload["worker_lifecycle_decision"]["execution"]["kind"] == "launch_session"
    assert payload["worker_lifecycle_decision"]["execution"]["display_kind"] == "merge_dispatch"
```

- [ ] **Step 2: Run test and verify it fails because execution is None**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/integration/supervisor/test_supervisor_merge_dispatch_loop.py::test_supervisor_loop_dispatches_merge_worker_for_ready_integration -q
```

Expected: FAIL with `TypeError: 'NoneType' object is not subscriptable`.

- [ ] **Step 3: Record merge dispatch execution into lifecycle decision**

Modify `src/isotope/features/supervisor/commands/supervise/execution.py`.

In `_append_supervise_llm_execution`, replace the `elif merge_dispatch is not None:` branch body with:

```python
        payload["executed"] = _merge_dispatch_executed(
            args,
            action_report,
            payload,
            merge_dispatch,
            api=api,
        )
        lifecycle_decision = payload.get("worker_lifecycle_decision")
        if isinstance(lifecycle_decision, dict):
            lifecycle_decision["execution"] = payload["executed"]
        api._refresh_current_batch_after_execution(
            args,
            payload,
            executed=payload["executed"],
            active_goals=active_goals,
            worker_reviews=worker_reviews,
        )
```

- [ ] **Step 4: Run targeted test and verify it passes**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/integration/supervisor/test_supervisor_merge_dispatch_loop.py::test_supervisor_loop_dispatches_merge_worker_for_ready_integration -q
```

Expected: `1 passed`.

- [ ] **Step 5: Run regression set**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/features/supervisor/test_worker_lifecycle_decision.py \
  tests/integration/supervisor/test_supervisor_merge_dispatch_loop.py \
  tests/integration/supervisor/test_supervisor_auto_loop_e2e.py -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit Task 3**

Run:

```bash
git add src/isotope/features/supervisor/commands/supervise/execution.py \
  tests/integration/supervisor/test_supervisor_merge_dispatch_loop.py
git commit -m "feat(supervisor): track lifecycle merge execution"
```

## Task 4: Final Verification And Prompt-Debt Note

**Files:**
- Modify: `docs/superpowers/specs/2026-06-04-supervisor-worker-lifecycle-decision-design.md`

- [ ] **Step 1: Update spec with implementation checkpoint**

Append this section to `docs/superpowers/specs/2026-06-04-supervisor-worker-lifecycle-decision-design.md`:

```markdown
## Implementation Checkpoint

The first implementation slice adds the decision module, exposes `worker_lifecycle_decision` in supervisor loop payloads, and records merge dispatch execution into that decision. Prompt slimming remains the next slice after payload and execution behavior are stable in tests.
```

- [ ] **Step 2: Run full targeted verification**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/features/supervisor/test_worker_lifecycle_decision.py \
  tests/unit/features/supervisor/test_supervisor_merge_work_order.py \
  tests/integration/supervisor/test_supervisor_merge_dispatch_loop.py \
  tests/integration/supervisor/test_supervisor_auto_loop_e2e.py -q
```

Expected: all selected tests pass.

- [ ] **Step 3: Inspect git status and recent commits**

Run:

```bash
git status --short --branch
git log --oneline -5
```

Expected: working tree clean after commit; recent commits show the design commit plus three implementation commits.

- [ ] **Step 4: Commit checkpoint doc**

Run:

```bash
git add docs/superpowers/specs/2026-06-04-supervisor-worker-lifecycle-decision-design.md
git commit -m "docs(supervisor): record lifecycle decision checkpoint"
```

## Self-Review

Spec coverage:

- Pure decision layer: Task 1.
- Payload exposure before behavior change: Task 2.
- Deterministic merge dispatch execution tracking: Task 3.
- Prompt slimming deferred explicitly as next slice: Task 4.
- Safety boundaries for conflict, CI retry, and cleanup deletion remain unchanged in this slice.

Placeholder scan:

- This plan contains no placeholder markers or open-ended implementation steps.

Type consistency:

- Public function name is `build_worker_lifecycle_decision`.
- Payload key is `worker_lifecycle_decision`.
- Decision actions are `monitor`, `dispatch_merge`, `archive_integrated`, and `needs_human` in this slice.
