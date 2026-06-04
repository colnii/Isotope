# QQ Replay Expectations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let QQ replay files declare pass/fail expectations so operators can gate persona/sticker behavior before real group runs.

**Architecture:** Extend `src/isotope/features/social/replay.py` with expectation parsing/evaluation over the existing replay report summary. Keep `qq replay` on the same dry-run runtime path and add `passed` plus expectation results to the report and CLI JSON.

**Tech Stack:** Python 3.13, argparse, pathlib, json, pytest, existing QQ social replay runtime.

---

### Task 1: Replay Template Expectations

**Files:**
- Modify: `src/isotope/features/social/replay.py`
- Test: `tests/unit/features/social/test_social_runner.py`

- [x] **Step 1: Write failing template assertion**

Extend `test_social_runner_qq_init_replay_writes_editable_event_file` to assert generated replay JSON includes:

```json
{
  "expectations": {
    "require_processed_events": 2,
    "min_proposed_actions": 1,
    "min_sticker_candidates": 1,
    "max_send_feedback": 0,
    "max_sent_group_messages": 0,
    "require_all_dry_run": true
  }
}
```

- [x] **Step 2: Verify red**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_runner.py::test_social_runner_qq_init_replay_writes_editable_event_file -q
```

Expected: FAIL because generated replay files do not include expectations.

- [x] **Step 3: Implement template expectations**

Add default expectations to the replay template.

- [x] **Step 4: Verify green**

Run the focused template test again. Expected: PASS.

### Task 2: Expectation Evaluation

**Files:**
- Modify: `src/isotope/features/social/replay.py`
- Modify: `src/isotope/features/social/runner.py`
- Test: `tests/unit/features/social/test_social_runner.py`

- [x] **Step 1: Write failing replay expectation test**

Extend `test_social_runner_qq_replay_writes_decision_report` to assert:

- CLI JSON includes `passed: true`;
- report includes `passed: true`;
- report includes expectation results for all default rules;
- every expectation result has `ok: true`.

- [x] **Step 2: Verify red**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_runner.py::test_social_runner_qq_replay_writes_decision_report -q
```

Expected: FAIL because replay reports do not include expectation results.

- [x] **Step 3: Implement evaluator**

Add `evaluate_expectations(expectations, report)` or equivalent helper in `replay.py`. Supported rules:

- `require_processed_events`
- `min_proposed_actions`
- `min_sticker_candidates`
- `max_send_feedback`
- `max_sent_group_messages`
- `require_all_dry_run`

Each result should include `name`, `ok`, `expected`, and `actual`.

- [x] **Step 4: Wire report and CLI JSON**

`build_replay_report(...)` should include `expectations` and `passed`. `_handle_replay` should return both.

- [x] **Step 5: Verify green**

Run the focused replay test again. Expected: PASS.

### Task 3: Docs and Regression

**Files:**
- Modify: `docs/current/qq-group-chatbot.md`
- Modify: `docs/current/qq-group-chatbot-operations.md`
- Modify: `tests/unit/docs/test_qq_group_chatbot_docs.py`

- [x] **Step 1: Add docs assertion**

Require docs to mention `expectations`, `passed`, `min_sticker_candidates`, and `require_all_dry_run`.

- [x] **Step 2: Update runbooks**

Document that replay files can declare expectation rules and that operators must treat `passed: false` as a blocker before live dry-run.

- [x] **Step 3: Final verification**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_runner.py tests/unit/features/social tests/integration/social/test_qq_runtime_wiring.py tests/integration/social/test_social_fake_platform_flow.py tests/unit/integrations/qq/test_onebot_adapter.py tests/unit/integrations/qq/test_onebot_ws_client.py tests/integration/qq/test_fake_onebot_flow.py tests/unit/docs/test_qq_group_chatbot_docs.py -q
git diff --check
```

Expected: tests pass and whitespace check has no output.

### Acceptance Standard

- A generated replay file contains explicit pass/fail expectations.
- `qq replay` reports `passed` and per-rule results.
- Failed expectations are visible in the report and CLI JSON.
- Replay remains dry-run and never sends QQ messages by default.
