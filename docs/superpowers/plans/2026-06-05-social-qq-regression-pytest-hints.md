# QQ Regression Pytest Hints Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make QQ beta failure intake tell operators which pytest regression target to update or run after a replay draft is generated.

**Architecture:** Reuse the existing `regression_test` field in failure records and replay metadata. Add that field to the regression intake index, derive a repo-root pytest command, and teach generated scripts to accept a third positional regression-test path and print the next pytest command. The feature must only produce guidance and files; it must not run pytest automatically, connect to OneBot, send messages, or close failures.

**Tech Stack:** Python 3.13, pytest, generated bash scripts, existing `isotope-social qq record-failure`, `regression-intake`, and `replay` commands.

---

### Task 1: Intake Index And Script Guidance

**Files:**
- Modify: `src/isotope/features/social/regression_intake.py`
- Modify: `src/isotope/features/social/beta_pack.py`
- Modify: `tests/unit/features/social/test_social_runner.py`
- Modify: `tests/unit/docs/test_qq_group_chatbot_docs.py`
- Modify: `docs/current/qq-group-chatbot-operations.md`

- [ ] **Step 1: Write failing regression intake assertions**

Extend `test_social_runner_qq_regression_intake_writes_replay_drafts` to assert the public intake draft includes:

```python
assert index["drafts"][0]["regression_test"] == "tests/integration/social/test_social_fake_platform_flow.py"
assert index["drafts"][0]["pytest_command"] == (
    "PYTHONPATH=src .venv/bin/python -m pytest "
    "tests/integration/social/test_social_fake_platform_flow.py -q"
)
```

- [ ] **Step 2: Write failing generated script assertions**

Extend generated pack tests so `record-failure.sh` reads a third positional argument into `regression_test`, and `failure-to-regression.sh` prints `Next pytest command(s):` plus the pytest command when invoked as:

```bash
./failure-to-regression.sh "表情包过度热情" "这能发吗" "tests/integration/qq/test_fake_onebot_flow.py"
```

- [ ] **Step 3: Verify red**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/features/social/test_social_runner.py::test_social_runner_qq_regression_intake_writes_replay_drafts \
  tests/unit/features/social/test_social_runner.py::test_social_runner_qq_init_beta_writes_operator_pack \
  tests/unit/features/social/test_social_runner.py::test_social_runner_qq_failure_to_regression_script_records_and_drafts \
  tests/unit/docs/test_qq_group_chatbot_docs.py -q
```

Expected: failures mention missing `regression_test`, `pytest_command`, or generated script guidance.

- [ ] **Step 4: Implement intake metadata**

In `regression_intake.py`, add:

- `_regression_test(failure)` returning the stripped `regression_test` string.
- `_pytest_command(regression_test)` returning `PYTHONPATH=src .venv/bin/python -m pytest <path> -q`, shell-quoting the path.

Include both values in each public draft. Leave blank values out or as empty strings consistently.

- [ ] **Step 5: Implement generated script guidance**

In `beta_pack.py`:

- Make `record-failure.sh` accept `REGRESSION_TEST="${3:-${ISOTOPE_QQ_FAILURE_REGRESSION_TEST:-}}"`.
- Update the usage line to show `[regression_test]`.
- Make `failure-to-regression.sh` print `Next pytest command(s):` and every non-empty `pytest_command` from `logs/regression-intake.json`.

- [ ] **Step 6: Update docs and docs test**

Mention the third positional argument and require `pytest_command` in docs coverage.

- [ ] **Step 7: Verify focused behavior passes**

Run the same focused command from Step 3. Expected: all selected tests pass.

### Task 2: Final Verification And Merge

**Files:**
- Verify: `src/isotope/features/social/regression_intake.py`
- Verify: `src/isotope/features/social/beta_pack.py`
- Verify: `tests/unit/features/social/test_social_runner.py`
- Verify: `docs/current/qq-group-chatbot-operations.md`
- Verify: `tests/unit/docs/test_qq_group_chatbot_docs.py`

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
git commit -m "feat(social): print qq regression pytest hints"
```

Then rebase on latest `origin/main` if needed, fast-forward merge to `main`, push, remove the temporary worktree, and delete the local feature branch.
