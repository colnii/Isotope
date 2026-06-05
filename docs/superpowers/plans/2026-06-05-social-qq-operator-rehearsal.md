# QQ Operator Rehearsal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a generated QQ beta pack rehearsal script that runs the local operator closeout chain without connecting to QQ or enabling sends.

**Architecture:** Reuse generated scripts and existing report commands. The rehearsal writes minimal local artifacts for dry-run review and exported audit log, records one rehearsal failure, drafts regression replay commands, closes that failure, regenerates regression intake, writes beta-day report, and writes beta-closeout. It must not call `live-run`, `dry-run`, `send-run`, or OneBot.

**Tech Stack:** Python 3.13, pytest, generated bash scripts, existing `isotope-social qq` commands.

---

### Task 1: Generated Rehearsal Script

**Files:**
- Modify: `src/isotope/features/social/beta_pack.py`
- Modify: `tests/unit/features/social/test_social_runner.py`
- Modify: `tests/unit/docs/test_qq_group_chatbot_docs.py`
- Modify: `docs/current/qq-group-chatbot-operations.md`

- [x] **Step 1: Write failing generated pack assertions**

Extend `test_social_runner_qq_init_beta_writes_operator_pack` to require `operator-rehearsal.sh`. Assert the script mentions `failure-to-regression.sh`, `close-failure.sh`, `regression-intake.sh`, `beta-day-report.sh`, and `beta-closeout.sh`; assert it does not contain `live-run`, `dry-run.sh`, or `send-run.sh`.

- [x] **Step 2: Write failing behavior test**

Generate a beta pack and run:

```bash
ISOTOPE_QQ_REHEARSAL_DATE=2026-06-06 ./operator-rehearsal.sh
```

Assert:

- `logs/dry-run-review.json` exists.
- `logs/qq-99999.json` exists.
- `logs/failures.json` contains one `fixed` failure with `resolved_date: 2026-06-06`.
- `logs/regression-intake.json` has `draft_count: 0`.
- `logs/beta-day-report.json` has `summary.open_failure_count: 0` and `ready_for_send: true`.
- `logs/beta-closeout.json` has `can_enter_send_run: true`.

- [x] **Step 3: Update docs coverage**

Require docs to mention `operator-rehearsal.sh`, `ISOTOPE_QQ_REHEARSAL_DATE`, and `operator_rehearsal`.

- [x] **Step 4: Verify red**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/features/social/test_social_runner.py::test_social_runner_qq_init_beta_writes_operator_pack \
  tests/unit/features/social/test_social_runner.py::test_social_runner_qq_operator_rehearsal_script_runs_local_closeout_chain \
  tests/unit/docs/test_qq_group_chatbot_docs.py -q
```

Expected: failure because `operator-rehearsal.sh` is missing.

- [x] **Step 5: Implement generated script**

In `beta_pack.py`, add `operator-rehearsal.sh` to `SCRIPT_NAMES` and generate a script that:

- runs diagnostics with output under `logs/operator-rehearsal-diagnostics.json` but does not stop if diagnostics reports not ready;
- writes local `logs/dry-run-review.json` and `logs/qq-<group>.json`;
- runs `failure-to-regression.sh`;
- runs `close-failure.sh qq-failure-1 ...`;
- runs `regression-intake.sh` again;
- runs `beta-day-report.sh`;
- runs `beta-closeout.sh`;
- prints the resulting `logs/beta-closeout.json`.

- [x] **Step 6: Verify focused tests pass**

Run the focused command from Step 4. Expected: all selected tests pass.

### Task 2: Final Verification And Merge

**Files:**
- Verify social feature files, docs, and tests.

- [x] **Step 1: Run related QQ/social tests**

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/features/social \
  tests/unit/llm/test_system_prompt_assets.py \
  tests/unit/integrations/qq/test_onebot_adapter.py \
  tests/unit/integrations/qq/test_onebot_ws_client.py \
  tests/integration/social/test_qq_runtime_wiring.py \
  tests/integration/social/test_social_fake_platform_flow.py \
  tests/integration/qq/test_fake_onebot_flow.py \
  tests/unit/docs/test_qq_group_chatbot_docs.py -q
```

Expected: all selected tests pass, with only the existing real QQ smoke skip if environment variables are absent.

- [x] **Step 2: Run whitespace check**

```bash
git diff --check
```

Expected: no output and exit code 0.

- [ ] **Step 3: Commit, fast-forward merge, push, and clean worktree**

Commit with:

```bash
git commit -m "feat(social): add qq operator rehearsal script"
```

Then rebase on latest `origin/main` if needed, fast-forward merge to `main`, push, remove the temporary worktree, and delete the local feature branch.
