# QQ Failure To Regression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a generated QQ beta pack script that turns one observed beta failure into a structured failure record plus replay regression draft, then prints the exact replay command for operator review.

**Architecture:** Reuse the existing generated `record-failure.sh` and `regression-intake.sh` scripts as the source of behavior. The new `failure-to-regression.sh` is an operator workflow wrapper: record, intake, print next replay commands. It must not connect to OneBot and must not send QQ messages.

**Tech Stack:** Python 3.13, pytest, generated bash scripts, `isotope-social qq record-failure`, `isotope-social qq regression-intake`, `isotope-social qq replay`.

---

### Task 1: Generated Script Contract

**Files:**
- Modify: `tests/unit/features/social/test_social_runner.py`
- Modify: `tests/unit/docs/test_qq_group_chatbot_docs.py`
- Modify: `src/isotope/features/social/beta_pack.py`
- Modify: `docs/current/qq-group-chatbot-operations.md`

- [ ] **Step 1: Write the failing generated-pack test**

Add `failure-to-regression.sh` to the expected script list in `test_social_runner_qq_init_beta_writes_operator_pack`, then assert the generated script:

```python
failure_to_regression = (output_dir / "failure-to-regression.sh").read_text(
    encoding="utf-8"
)
assert "./record-failure.sh" in failure_to_regression
assert "./regression-intake.sh" in failure_to_regression
assert "qq replay" in failure_to_regression
assert "--replay-json" in failure_to_regression
assert "live-run" not in failure_to_regression
assert "send-run" not in failure_to_regression
```

- [ ] **Step 2: Write the failing end-to-end script test**

Add a test that generates a beta pack, runs:

```bash
./failure-to-regression.sh "表情包过度热情" "这能发吗"
```

with `ISOTOPE_QQ_FAILURE_DATE=2026-06-05`, then asserts:

```python
assert result.returncode == 0
combined_output = result.stdout + result.stderr
assert "qq replay" in combined_output
assert "--replay-json" in combined_output
assert "regressions/qq-failure-1.replay.json" in combined_output
assert "live-run" not in combined_output
assert "send-run" not in combined_output
assert _read_json(output_dir / "logs" / "failures.json")["failures"][0]["symptom"] == "表情包过度热情"
assert _read_json(output_dir / "logs" / "regression-intake.json")["draft_count"] == 1
assert (output_dir / "regressions" / "qq-failure-1.replay.json").is_file()
```

- [ ] **Step 3: Verify the tests fail for the missing feature**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/unit/features/social/test_social_runner.py::test_social_runner_qq_init_beta_writes_operator_pack \
  tests/unit/features/social/test_social_runner.py::test_social_runner_qq_failure_to_regression_script_records_and_drafts \
  tests/unit/docs/test_qq_group_chatbot_docs.py -q
```

Expected: failure mentioning missing `failure-to-regression.sh` in the generated scripts or docs.

- [ ] **Step 4: Implement the generated script**

In `src/isotope/features/social/beta_pack.py`:

- Add `"failure-to-regression.sh"` to `SCRIPT_NAMES`.
- Add a `_script_body` branch for that name.
- Add `_failure_to_regression_command(config)` that runs `./record-failure.sh "$@"`, runs `./regression-intake.sh`, reads `logs/regression-intake.json` with Python stdlib JSON parsing, and prints `isotope-social qq replay --config-json config.json --state-root state --replay-json <draft> --output logs/replay-report.json --json` for each draft.

- [ ] **Step 5: Update operator docs**

In `docs/current/qq-group-chatbot-operations.md`, document the generated pack shortcut:

```bash
./failure-to-regression.sh "表情包过度热情" "这能发吗"
```

State that it records the issue, drafts replay files, prints replay commands, and does not connect or send.

- [ ] **Step 6: Verify focused behavior passes**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/unit/features/social/test_social_runner.py::test_social_runner_qq_init_beta_writes_operator_pack \
  tests/unit/features/social/test_social_runner.py::test_social_runner_qq_failure_to_regression_script_records_and_drafts \
  tests/unit/docs/test_qq_group_chatbot_docs.py -q
```

Expected: all selected tests pass.

### Task 2: Regression Verification And Finish

**Files:**
- Verify: `src/isotope/features/social/beta_pack.py`
- Verify: `tests/unit/features/social/test_social_runner.py`
- Verify: `docs/current/qq-group-chatbot-operations.md`
- Verify: `tests/unit/docs/test_qq_group_chatbot_docs.py`

- [ ] **Step 1: Run relevant QQ/social regression tests**

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
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

- [ ] **Step 2: Run whitespace diff check**

```bash
git diff --check
```

Expected: no output and exit code 0.

- [ ] **Step 3: Commit**

```bash
git status --short
git diff -- src/isotope/features/social/beta_pack.py tests/unit/features/social/test_social_runner.py docs/current/qq-group-chatbot-operations.md tests/unit/docs/test_qq_group_chatbot_docs.py docs/superpowers/plans/2026-06-05-social-qq-failure-to-regression.md
git add src/isotope/features/social/beta_pack.py tests/unit/features/social/test_social_runner.py docs/current/qq-group-chatbot-operations.md tests/unit/docs/test_qq_group_chatbot_docs.py docs/superpowers/plans/2026-06-05-social-qq-failure-to-regression.md
git commit -m "feat(social): add qq failure regression script"
```

- [ ] **Step 4: Merge and clean worktree**

From the main checkout, fast-forward merge the feature branch, push `main`, then remove `.worktrees/social-qq-failure-to-regression` and delete the local feature branch.
