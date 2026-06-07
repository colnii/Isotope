# QQ Diagnostics Replay Scenarios Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development or superpowers:executing-plans to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for
> tracking.

**Goal:** Make beta diagnostics surface replay scenario report readiness and
next steps.

**Architecture:** Extend diagnostics summary and next-step logic while reusing
startup-check validation for scenario aggregate reports.

**Tech Stack:** Python 3.13, pytest, existing social CLI tests.

---

### Task 1: Diagnostics Scenario Report

**Files:**

- Modify: `src/isotope/features/social/beta_diagnostics.py`
- Add: `tests/unit/features/social/test_social_qq_diagnostics_scenarios.py`
- Modify: `tests/unit/features/social/test_social_runner_profile_startup.py`
- Modify: `tests/unit/docs/test_qq_group_chatbot_docs.py`
- Modify: `docs/current/qq-group-chatbot.md`
- Modify: `docs/current/qq-group-chatbot-operations.md`

- [x] **Step 1: Write failing tests**

Add tests for missing, failed, and passing `replay-scenarios-report.json`.

- [x] **Step 2: Verify red**

Run the new focused tests and confirm diagnostics still reports ready without
scenario readiness.

- [x] **Step 3: Extend diagnostics**

Add `replay_scenarios_report` summary, pass the scenario report path into
startup gate checks, and make readiness require both reports.

- [x] **Step 4: Add next steps**

Guide missing scenario reports with `create_replay_scenarios` and
`run_replay_scenarios`; include both replay report args in fix-startup-check.

- [x] **Step 5: Update docs**

Document diagnostics summary and next-step names.

- [x] **Step 6: Verify and prepare integration**

Run focused tests, relevant social/QQ tests, and `git diff --check`, then
commit the branch for fast-forward merge, push, and worktree cleanup.
