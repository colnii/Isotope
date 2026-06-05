# QQ Beta Closeout Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a QQ beta closeout report that combines the beta-day report and regression-intake index into one operator checklist for deciding whether send-run can be enabled.

**Architecture:** Reuse existing artifacts: `logs/beta-day-report.json`, `logs/regression-intake.json`, and generated scripts. The new report is read-only: it summarizes warnings, open failures, closed failures, pending replay drafts, pending pytest commands, and a final `can_enter_send_run` boolean. It does not connect to OneBot, send messages, run replay, run pytest, or mutate failures.

**Tech Stack:** Python 3.13, pytest, argparse, pathlib/json, generated bash scripts.

---

### Task 1: Closeout CLI Contract

**Files:**
- Create: `src/isotope/features/social/beta_closeout.py`
- Modify: `src/isotope/features/social/qq_beta_commands.py`
- Modify: `src/isotope/features/social/qq_runner.py`
- Modify: `src/isotope/features/social/qq_handlers.py`
- Modify: `tests/unit/features/social/test_social_runner.py`

- [ ] **Step 1: Write failing blocked closeout test**

Add a test that writes a `beta-day-report.json` with `ready_for_send: false`, one warning, one open failure, and a `regression-intake.json` with one draft and pytest command. Run:

```bash
isotope-social qq beta-closeout \
  --beta-day-report <beta-day-report.json> \
  --regression-intake <regression-intake.json> \
  --output <beta-closeout.json> --json
```

Assert `can_enter_send_run` is false, blockers include `review_dry_run_warnings`, `open_failures`, and `pending_regression_drafts`, and the output contains replay/pytest commands from intake.

- [ ] **Step 2: Write failing ready closeout test**

Add a test with `ready_for_send: true`, zero warnings, only fixed failures, and zero draft intake. Assert `can_enter_send_run` is true and next actions include `operator_review_before_send`.

- [ ] **Step 3: Verify red**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/features/social/test_social_runner.py::test_social_runner_qq_beta_closeout_blocks_open_failures_and_drafts \
  tests/unit/features/social/test_social_runner.py::test_social_runner_qq_beta_closeout_allows_operator_send_review -q
```

Expected: failure because `beta-closeout` is not registered.

- [ ] **Step 4: Implement closeout module**

Create `beta_closeout.py` with:

- `QQBetaCloseoutConfig(beta_day_report, regression_intake, output)`
- `build_qq_beta_closeout(config)`
- `write_qq_beta_closeout(path, report)`

Report shape:

- `kind: qq_beta_closeout`
- `can_enter_send_run`
- `blockers`
- `summary`
- `checklist`
- `pending_replay_commands`
- `pending_pytest_commands`
- `next_actions`

- [ ] **Step 5: Wire CLI**

Add `qq beta-closeout` with `--beta-day-report`, `--regression-intake`, `--output`, and `--json`. Return `can_enter_send_run`, `blockers`, `summary`, and `next_actions`.

- [ ] **Step 6: Verify focused CLI tests pass**

Run the focused command from Step 3. Expected: both tests pass.

### Task 2: Generated Script And Docs

**Files:**
- Modify: `src/isotope/features/social/beta_pack.py`
- Modify: `tests/unit/features/social/test_social_runner.py`
- Modify: `tests/unit/docs/test_qq_group_chatbot_docs.py`
- Modify: `docs/current/qq-group-chatbot-operations.md`

- [ ] **Step 1: Write failing generated pack assertions**

Extend `test_social_runner_qq_init_beta_writes_operator_pack` to require `beta-closeout.sh` and assert it calls `qq beta-closeout`, reads `logs/beta-day-report.json`, reads `logs/regression-intake.json`, and writes `logs/beta-closeout.json`.

- [ ] **Step 2: Write failing generated script behavior test**

Generate a pack, create minimal `logs/beta-day-report.json` and `logs/regression-intake.json`, run `./beta-closeout.sh`, and assert `logs/beta-closeout.json` exists with `can_enter_send_run`.

- [ ] **Step 3: Update docs coverage**

Require docs to mention `beta-closeout`, `beta-closeout.sh`, `beta-closeout.json`, `can_enter_send_run`, and `pending_regression_drafts`.

- [ ] **Step 4: Verify red**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/features/social/test_social_runner.py::test_social_runner_qq_init_beta_writes_operator_pack \
  tests/unit/features/social/test_social_runner.py::test_social_runner_qq_beta_closeout_script_writes_operator_report \
  tests/unit/docs/test_qq_group_chatbot_docs.py -q
```

Expected: failure because script and docs are missing.

- [ ] **Step 5: Generate script and docs**

Add `beta-closeout.sh` to generated packs. It runs:

```bash
isotope-social qq beta-closeout \
  --beta-day-report logs/beta-day-report.json \
  --regression-intake logs/regression-intake.json \
  --output logs/beta-closeout.json --json
```

- [ ] **Step 6: Verify generated script tests pass**

Run the focused command from Step 4. Expected: all selected tests pass.

### Task 3: Final Verification And Merge

**Files:**
- Verify social feature files, docs, and tests.

- [ ] **Step 1: Run related QQ/social tests**

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

- [ ] **Step 2: Run whitespace check**

```bash
git diff --check
```

Expected: no output and exit code 0.

- [ ] **Step 3: Commit, fast-forward merge, push, and clean worktree**

Commit with:

```bash
git commit -m "feat(social): add qq beta closeout report"
```

Then rebase on latest `origin/main` if needed, fast-forward merge to `main`, push, remove the temporary worktree, and delete the local feature branch.
