# QQ Dry-Run Review Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate an operator-facing QQ dry-run review report from recorded decisions so beta operators can judge role behavior, silence, sticker candidates, and send readiness before enabling sends.

**Architecture:** Reuse the existing live-run state file and decision audit entries as the source of truth. Add a focused `dry_run_review.py` module that summarizes decision payloads into review turns, warnings, and counts. Wire a new `qq review-dry-run` CLI command and update generated beta packs to include `review-dry-run.sh` after `dry-run.sh`.

**Tech Stack:** Python 3.13, argparse, pathlib, json, pytest, existing QQ social runtime and audit state.

---

### Task 1: Review Report Builder

**Files:**
- Create: `src/isotope/features/social/dry_run_review.py`
- Modify: `tests/unit/features/social/test_social_runner.py`

- [x] **Step 1: Write failing builder test through CLI**

Add a test that runs `qq live-run` in dry-run mode with `FakeLiveOneBotClient`, then runs:

```bash
isotope-social qq review-dry-run --state-root <state> \
  --group 99999 --output <report.json> --json
```

Assert the CLI returns:

```json
{
  "status": "ok",
  "command": "review-dry-run",
  "ready_for_send": false,
  "summary": {
    "decision_count": 1,
    "dry_run_decision_count": 1,
    "proposed_action_count": 1,
    "selected_action_count": 0,
    "sticker_candidate_count": 1
  }
}
```

Also assert the written report has `kind: qq_dry_run_review`, one turn, the proposed candidate reason, sticker candidate details, and a warning that dry-run candidates were not selected for sending.

- [x] **Step 2: Verify red**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_runner.py::test_social_runner_qq_review_dry_run_writes_operator_report -q
```

Expected: FAIL because `review-dry-run` is not registered.

- [x] **Step 3: Implement review module**

Create `src/isotope/features/social/dry_run_review.py` with:

- `QQDryRunReviewConfig(state_file: Path, group_id: str, output: Path)`
- `build_qq_dry_run_review(config)` that reads `social-qq-state.json`
- `write_qq_dry_run_review(path, report)`

Report fields:

- `kind`
- `state_file`
- `group_id`
- `ready_for_send`
- `summary`
- `turns`
- `warnings`

- [x] **Step 4: Verify module through CLI after runner wiring**

Run the focused test after Task 2. Expected: PASS.

### Task 2: CLI and Generated Beta Pack Script

**Files:**
- Modify: `src/isotope/features/social/runner.py`
- Modify: `src/isotope/features/social/beta_pack.py`
- Modify: `tests/unit/features/social/test_social_runner.py`

- [x] **Step 1: Write failing script assertion**

Extend the init-beta test to assert generated scripts include `review-dry-run.sh`, and that it calls:

```bash
isotope-social qq review-dry-run --state-root state --group <group_id> \
  --output logs/dry-run-review.json --json
```

- [x] **Step 2: Verify red**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_runner.py::test_social_runner_qq_init_beta_writes_operator_pack -q
```

Expected: FAIL because `review-dry-run.sh` is not generated.

- [x] **Step 3: Wire CLI command**

Add `qq review-dry-run` with `--state-root`, `--group`, `--output`, and `--json`. It should call `build_qq_dry_run_review`, write the report, and return `summary`, `ready_for_send`, and `output`.

- [x] **Step 4: Generate script**

Add `review-dry-run.sh` to `SCRIPT_NAMES`. It should run after `dry-run.sh` in the beta README first-run order and write `logs/dry-run-review.json`.

- [x] **Step 5: Verify green**

Run both focused tests. Expected: PASS.

### Task 3: Docs and Regression

**Files:**
- Modify: `docs/current/qq-group-chatbot.md`
- Modify: `docs/current/qq-group-chatbot-operations.md`
- Modify: `tests/unit/docs/test_qq_group_chatbot_docs.py`
- Modify: `docs/current/refactoring-debt.md` only if `runner.py` grows further without a split

- [x] **Step 1: Add docs assertion**

Require docs to mention `review-dry-run`, `dry-run-review.json`, `ready_for_send`, `sticker_candidate_count`, and `warnings`.

- [x] **Step 2: Update runbooks**

Document the review step after `./dry-run.sh` and before `ISOTOPE_QQ_ENABLE_SEND=1 ./send-run.sh`. Explain that `ready_for_send` is only a report field, not permission to send; the operator must still inspect warnings and manually set the env var.

- [x] **Step 3: Final verification**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_runner.py tests/unit/features/social tests/integration/social/test_qq_runtime_wiring.py tests/integration/social/test_social_fake_platform_flow.py tests/unit/integrations/qq/test_onebot_adapter.py tests/unit/integrations/qq/test_onebot_ws_client.py tests/integration/qq/test_fake_onebot_flow.py tests/unit/docs/test_qq_group_chatbot_docs.py -q
git diff --check
```

Expected: tests pass and whitespace check has no output.

### Acceptance Standard

- Operators can generate `dry-run-review.json` from real dry-run state.
- The report shows why the bot spoke or stayed silent, proposed/selected action counts, sticker candidate count, and warnings.
- Generated beta packs include a review script in the normal operator path.
- The report never grants send permission by itself; sends still require manual `ISOTOPE_QQ_ENABLE_SEND=1`.
