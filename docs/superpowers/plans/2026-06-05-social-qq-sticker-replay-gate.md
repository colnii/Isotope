# QQ Sticker Replay Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add concrete sticker ID expectations to QQ replay reports.

**Architecture:** Extend the existing replay expectation evaluator. Extract
sticker IDs from proposed and selected reply candidates, expose them in the
summary, and evaluate new expectation fields against that summary.

**Tech Stack:** Python 3.13, pytest, existing `isotope-social qq replay`.

---

### Task 1: Replay Sticker ID Expectations

**Files:**
- Modify: `src/isotope/features/social/replay.py`
- Modify: `tests/unit/features/social/test_social_runner.py`
- Modify: `tests/unit/docs/test_qq_group_chatbot_docs.py`
- Modify: `docs/current/qq-group-chatbot.md`
- Modify: `docs/current/qq-group-chatbot-operations.md`

- [x] **Step 1: Write failing replay tests**

Require generated replay defaults to include:

```json
{
  "require_sticker_candidate_ids": ["ship-it"],
  "forbid_sticker_candidate_ids": [],
  "max_selected_sticker_actions": 0
}
```

Extend the passing replay test to assert the summary contains `ship-it` in
`sticker_candidate_ids`, no `selected_sticker_ids`, and
`selected_sticker_action_count == 0`. Extend the failed expectation test to
require `missing-sticker` and forbid `ship-it`.

- [x] **Step 2: Verify red**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/features/social/test_social_runner.py::test_social_runner_qq_init_replay_writes_editable_event_file \
  tests/unit/features/social/test_social_runner.py::test_social_runner_qq_replay_writes_decision_report \
  tests/unit/features/social/test_social_runner.py::test_social_runner_qq_replay_reports_failed_expectations -q
```

Expected: failures because the replay summary and expectations do not expose
the new sticker ID fields yet.

- [x] **Step 3: Implement replay extraction and checks**

In `replay.py`, add the three new default expectation fields, collect proposed
and selected sticker IDs from candidate metadata or reply action platform data,
and evaluate list/int expectations with explicit failures for unsupported or
badly typed values.

- [x] **Step 4: Update docs coverage**

Document the new expectation fields in both QQ runbooks, and require the docs
test to mention them.

- [x] **Step 5: Verify focused and related tests**

Run the focused command from Step 2, then:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/features/social \
  tests/integration/social/test_social_fake_platform_flow.py \
  tests/unit/docs/test_qq_group_chatbot_docs.py -q
git diff --check
```
