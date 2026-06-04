# QQ Beta Day Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate a QQ beta day report that combines dry-run review, exported audit log, and operator failure records into one daily artifact.

**Architecture:** Reuse `dry_run_review.py` and `export-log` artifacts as inputs. Add a focused `beta_day_report.py` module that reads JSON artifacts, validates an optional failure-record file, computes a day summary, and writes a structured report. Wire a new `qq beta-day-report` CLI command and generated `beta-day-report.sh` script.

**Tech Stack:** Python 3.13, argparse, pathlib, json, pytest, existing QQ social beta pack/runtime modules.

---

### Task 1: Report Builder CLI Contract

**Files:**
- Create: `src/isotope/features/social/beta_day_report.py`
- Modify: `src/isotope/features/social/runner.py`
- Modify: `tests/unit/features/social/test_social_runner.py`

- [x] **Step 1: Write failing report test**

Add a test that writes:

- a `dry-run-review.json` with `summary`, `warnings`, and `ready_for_send`;
- an exported log JSON with `entries`;
- a `failures.json` with one open failure containing `symptom`, `root_cause`, and `regression_test`.

Run:

```bash
isotope-social qq beta-day-report --date 2026-06-04 --group 99999 \
  --dry-run-review <dry-run-review.json> --export-log <qq-99999.json> \
  --failures-json <failures.json> --output <beta-day-report.json> --json
```

Assert the CLI returns `status: ok`, `command: beta-day-report`, `ready_for_send: false`, `open_failure_count: 1`, and writes `kind: qq_beta_day_report`.

- [x] **Step 2: Verify red**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_runner.py::test_social_runner_qq_beta_day_report_combines_review_log_and_failures -q
```

Expected: FAIL because `beta-day-report` is not registered.

- [x] **Step 3: Implement builder module**

Create `src/isotope/features/social/beta_day_report.py` with:

- `QQBetaDayReportConfig(date, group_id, dry_run_review, export_log, failures_json, output)`
- `build_qq_beta_day_report(config)`
- `write_qq_beta_day_report(path, report)`

Report fields:

- `kind`
- `date`
- `group_id`
- `ready_for_send`
- `summary`
- `inputs`
- `review_warnings`
- `failures`
- `next_actions`

- [x] **Step 4: Wire CLI command**

Add `qq beta-day-report` with the arguments above. If `failures-json` is omitted, use no failures. Return `summary`, `ready_for_send`, `open_failure_count`, `output`, and `next_actions`.

- [x] **Step 5: Verify green**

Run the focused report test again. Expected: PASS.

### Task 2: Generated Script and Failure Template

**Files:**
- Modify: `src/isotope/features/social/beta_pack.py`
- Modify: `tests/unit/features/social/test_social_runner.py`

- [x] **Step 1: Write failing script assertion**

Extend the init-beta test to assert generated scripts include `beta-day-report.sh`, and that it calls:

```bash
isotope-social qq beta-day-report --date "${ISOTOPE_QQ_BETA_DATE:-$(date +%F)}" \
  --group <group_id> --dry-run-review logs/dry-run-review.json \
  --export-log logs/qq-<group_id>.json --failures-json logs/failures.json \
  --output logs/beta-day-report.json --json
```

Also assert `logs/failures.json` is created with `{"failures": []}`.

- [x] **Step 2: Verify red**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_runner.py::test_social_runner_qq_init_beta_writes_operator_pack -q
```

Expected: FAIL because the script and failure file are not generated.

- [x] **Step 3: Generate script and template**

Add `beta-day-report.sh` to `SCRIPT_NAMES`, write `logs/failures.json` during pack creation if missing, and update README first-run order to run `./beta-day-report.sh` after `./export-log.sh`.

- [x] **Step 4: Verify green**

Run the focused init-beta test again. Expected: PASS.

### Task 3: Docs and Regression

**Files:**
- Modify: `docs/current/qq-group-chatbot.md`
- Modify: `docs/current/qq-group-chatbot-operations.md`
- Modify: `tests/unit/docs/test_qq_group_chatbot_docs.py`
- Modify: `docs/current/refactoring-debt.md`

- [x] **Step 1: Add docs assertion**

Require docs to mention `beta-day-report`, `beta-day-report.json`, `failures.json`, `open_failure_count`, and `next_actions`.

- [x] **Step 2: Update runbooks**

Document the daily closeout order: dry-run review, export log, edit failures, beta-day-report, then regression tests for open failures.

- [x] **Step 3: Update refactoring debt**

Update the Social QQ CLI Runner debt note if `runner.py` remains over 700 lines after this command.

- [x] **Step 4: Final verification**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_runner.py tests/unit/features/social tests/integration/social/test_qq_runtime_wiring.py tests/integration/social/test_social_fake_platform_flow.py tests/unit/integrations/qq/test_onebot_adapter.py tests/unit/integrations/qq/test_onebot_ws_client.py tests/integration/qq/test_fake_onebot_flow.py tests/unit/docs/test_qq_group_chatbot_docs.py -q
git diff --check
```

Expected: tests pass and whitespace check has no output.

### Acceptance Standard

- Operators can close a beta day with one JSON report.
- The report includes review warnings, audit counts, open failures, and concrete next actions.
- Generated beta packs include `failures.json` and `beta-day-report.sh`.
- The report does not override send gates; it records beta readiness and unresolved work.
