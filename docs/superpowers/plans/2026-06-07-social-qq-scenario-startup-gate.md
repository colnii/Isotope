# QQ Replay Scenarios Startup Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development or superpowers:executing-plans to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for
> tracking.

**Goal:** Require the replay scenario aggregate report during generated QQ beta
startup checks.

**Architecture:** Extend startup gate validation with the aggregate scenario
report, then wire generated beta scripts to pass and require that report.

**Tech Stack:** Python 3.13, pytest, existing social CLI tests.

---

### Task 1: Startup Gate Scenario Report

**Files:**

- Modify: `src/isotope/features/social/startup_gate.py`
- Modify: `src/isotope/features/social/qq_runner.py`
- Modify: `src/isotope/features/social/qq_beta_commands.py`
- Modify: `src/isotope/features/social/beta_pack.py`
- Add: `tests/unit/features/social/test_social_qq_startup_scenarios.py`
- Modify: `tests/unit/docs/test_qq_group_chatbot_docs.py`
- Modify: `docs/current/qq-group-chatbot.md`
- Modify: `docs/current/qq-group-chatbot-operations.md`

- [x] **Step 1: Write failing tests**

Add tests for startup-check passing with a scenario report, blocking a failed
scenario report, generated script wiring, and first-run stopping before health.

- [x] **Step 2: Verify red**

Run the new focused tests and confirm failure is missing CLI/script support.

- [x] **Step 3: Extend startup gate**

Add optional `replay_scenarios_report` config and a
`replay_scenarios_report` check.

- [x] **Step 4: Wire CLI and scripts**

Add `--replay-scenarios-report` to `qq startup-check`, generated
`startup-check.sh`, and `first-run.sh`.

- [x] **Step 5: Update docs**

Document the scenario report startup gate in current docs and generated README.

- [x] **Step 6: Verify and prepare integration**

Run focused tests, relevant social/QQ tests, and `git diff --check`, then
commit the branch for fast-forward merge, push, and worktree cleanup.
