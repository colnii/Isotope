# QQ Close Failure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an operator command that marks a QQ beta failure as fixed after replay and pytest verification, while keeping the fix note and regression test path in `failures.json`.

**Architecture:** Extend the existing failure log module instead of adding a separate JSON editor. The new `qq close-failure` command updates exactly one matching failure by id first, then by same-group symptom. Generated beta packs get `close-failure.sh` for the common pack-local flow. Closing a failure only edits `logs/failures.json`; it does not send QQ messages, run replay, run pytest, or delete evidence.

**Tech Stack:** Python 3.13, pytest, argparse, generated bash scripts, existing QQ beta operations modules.

---

### Task 1: Failure Log Update Command

**Files:**
- Modify: `src/isotope/features/social/failure_log.py`
- Modify: `src/isotope/features/social/qq_beta_commands.py`
- Modify: `src/isotope/features/social/qq_runner.py`
- Modify: `src/isotope/features/social/qq_handlers.py`
- Modify: `tests/unit/features/social/test_social_runner.py`

- [ ] **Step 1: Write failing CLI close test**

Add a test that writes `failures.json` with one open failure:

```json
{
  "id": "qq-beta-1",
  "date": "2026-06-05",
  "group": "99999",
  "status": "open",
  "symptom": "表情包过度热情",
  "regression_test": "tests/integration/qq/test_fake_onebot_flow.py"
}
```

Run:

```bash
isotope-social qq close-failure \
  --failures-json <failures.json> \
  --group 99999 \
  --failure qq-beta-1 \
  --resolved-date 2026-06-06 \
  --fix "replay and pytest passed" \
  --regression-test tests/integration/qq/test_fake_onebot_flow.py \
  --json
```

Assert the command returns `status: ok`, `command: close-failure`, `failure.status: fixed`, `open_failure_count: 0`, and the JSON file has `resolved_date`, `fix`, and `regression_test`.

- [ ] **Step 2: Write failing not-found test**

Run `qq close-failure --failure missing` against a file with no matching failure and assert exit code `2` with `social_runner_error`.

- [ ] **Step 3: Verify red**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/features/social/test_social_runner.py::test_social_runner_qq_close_failure_marks_failure_fixed \
  tests/unit/features/social/test_social_runner.py::test_social_runner_qq_close_failure_reports_missing_match -q
```

Expected: failure because `close-failure` is not registered.

- [ ] **Step 4: Implement failure log update**

In `failure_log.py`, add:

- `QQCloseFailureConfig`
- `close_qq_beta_failure(config)`

Rules:

- `failure` matches `id` first.
- If no id matches, it matches `symptom` in the requested group.
- If no match, raise `ValueError("no matching failure: ...")`.
- If multiple matches, raise `ValueError("multiple matching failures: ...")`.
- Updated failure gets `status`, `resolved_date`, `fix`, and optional `regression_test`.
- Return `failures_json`, `failure_count`, `open_failure_count`, and `failure`.

- [ ] **Step 5: Wire CLI**

Add `qq close-failure` with:

- `--failures-json`
- `--group`
- `--failure`
- `--resolved-date`
- `--status`, default `fixed`, choices `fixed`, `resolved`, `closed`
- `--fix`
- `--regression-test`
- `--json`

Register handler key `close_failure`.

- [ ] **Step 6: Verify focused CLI tests pass**

Run the focused command from Step 3. Expected: both tests pass.

### Task 2: Generated Script And Docs

**Files:**
- Modify: `src/isotope/features/social/beta_pack.py`
- Modify: `tests/unit/features/social/test_social_runner.py`
- Modify: `tests/unit/docs/test_qq_group_chatbot_docs.py`
- Modify: `docs/current/qq-group-chatbot-operations.md`

- [ ] **Step 1: Write failing generated script test**

Extend `test_social_runner_qq_init_beta_writes_operator_pack` to require `close-failure.sh` and assert it calls `qq close-failure`, uses `logs/failures.json`, `ISOTOPE_QQ_CLOSE_FAILURE_DATE`, and `ISOTOPE_QQ_CLOSE_FAILURE_REGRESSION_TEST`.

- [ ] **Step 2: Write failing generated script behavior test**

Generate a pack, run `./failure-to-regression.sh ...`, then run:

```bash
./close-failure.sh qq-failure-1 "replay and pytest passed" tests/integration/qq/test_fake_onebot_flow.py
```

with `ISOTOPE_QQ_CLOSE_FAILURE_DATE=2026-06-06`, and assert `logs/failures.json` status is `fixed`, `open_failure_count` from a following `./beta-day-report.sh` is `0`, and `./regression-intake.sh` produces `draft_count: 0`.

- [ ] **Step 3: Update docs coverage**

Require `close-failure`, `close-failure.sh`, `resolved_date`, and `ISOTOPE_QQ_CLOSE_FAILURE_DATE` in docs tests.

- [ ] **Step 4: Verify red**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/features/social/test_social_runner.py::test_social_runner_qq_init_beta_writes_operator_pack \
  tests/unit/features/social/test_social_runner.py::test_social_runner_qq_close_failure_script_marks_failure_fixed \
  tests/unit/docs/test_qq_group_chatbot_docs.py -q
```

Expected: failure because script and docs are missing.

- [ ] **Step 5: Generate script and docs**

Add `close-failure.sh` to the beta pack scripts. The script takes:

```bash
./close-failure.sh <failure_id_or_symptom> <fix> [regression_test]
```

It passes `--status fixed`, `--resolved-date "${ISOTOPE_QQ_CLOSE_FAILURE_DATE:-$(date +%F)}"`, and prints JSON output.

- [ ] **Step 6: Verify generated script tests pass**

Run the focused command from Step 4. Expected: all selected tests pass.

### Task 3: Final Verification And Merge

**Files:**
- Verify: social feature files, docs, and tests.

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
git commit -m "feat(social): add qq failure closeout"
```

Then rebase on latest `origin/main` if needed, fast-forward merge to `main`, push, remove the temporary worktree, and delete the local feature branch.
