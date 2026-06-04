# QQ Regression Intake Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert open QQ beta failures into replay draft files and an operator intake report.

**Architecture:** Reuse the existing QQ replay JSON format and `qq replay` command. Add a focused `regression_intake.py` module that reads `failures.json`, writes one replay draft per open failure, and writes an index report. Wire a new `qq regression-intake` CLI command and generated `regression-intake.sh` script.

**Tech Stack:** Python 3.13, argparse, pathlib, json, pytest, existing QQ social beta pack/runtime modules.

---

### Task 1: Regression Intake CLI Contract

**Files:**
- Create: `src/isotope/features/social/regression_intake.py`
- Modify: `src/isotope/features/social/runner.py`
- Modify: `tests/unit/features/social/test_social_runner.py`

- [x] **Step 1: Write failing intake test**

Add a test that writes `failures.json` with one open failure containing `id`, `date`, `group`, `symptom`, `observed_input`, `root_cause`, and `regression_test`.

Run:

```bash
isotope-social qq regression-intake --group 99999 --bot-user-id bot_qq \
  --failures-json <failures.json> --output-dir <regressions> \
  --index-output <regression-intake.json> --json
```

Assert the CLI returns `status: ok`, `command: regression-intake`, `draft_count: 1`, and writes an index with `kind: qq_regression_intake`. Assert the generated replay draft has `schema_version: isotope.qq_replay.v1`, one event, group `99999`, an at-mention for `bot_qq`, and `raw_message` derived from the failure's `observed_input`.

- [x] **Step 2: Verify red**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_runner.py::test_social_runner_qq_regression_intake_writes_replay_drafts -q
```

Expected: FAIL because `regression-intake` is not registered.

- [x] **Step 3: Implement builder module**

Create `src/isotope/features/social/regression_intake.py` with:

- `QQRegressionIntakeConfig(group_id, bot_user_id, failures_json, output_dir, index_output)`
- `build_qq_regression_intake(config)`
- `write_qq_regression_intake(index_path, intake)`

Only failures whose `status` is not `closed`, `resolved`, or `fixed` produce replay drafts. Each draft should include default replay runtime, expectations, one event, and metadata linking back to the failure.

- [x] **Step 4: Wire CLI command**

Add `qq regression-intake` with `--group`, `--bot-user-id`, `--failures-json`, `--output-dir`, `--index-output`, and `--json`. Return `draft_count`, `open_failure_count`, `output_dir`, `index_output`, and generated draft paths.

- [x] **Step 5: Verify green**

Run the focused report test again. Expected: PASS.

### Task 2: Generated Script and Docs Contract

**Files:**
- Modify: `src/isotope/features/social/beta_pack.py`
- Modify: `tests/unit/features/social/test_social_runner.py`
- Modify: `tests/unit/docs/test_qq_group_chatbot_docs.py`

- [x] **Step 1: Write failing script assertion**

Extend the init-beta test to assert generated scripts include `regression-intake.sh`, and that it calls:

```bash
isotope-social qq regression-intake --group <group_id> --bot-user-id <bot_user_id> \
  --failures-json logs/failures.json --output-dir regressions \
  --index-output logs/regression-intake.json --json
```

Also assert the generated pack creates a `regressions/` directory.

- [x] **Step 2: Add docs assertion**

Require docs to mention `regression-intake`, `regression-intake.json`, and `regressions/`.

- [x] **Step 3: Verify red**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_runner.py::test_social_runner_qq_init_beta_writes_operator_pack tests/unit/docs/test_qq_group_chatbot_docs.py -q
```

Expected: FAIL because the script and docs are not updated yet.

- [x] **Step 4: Generate script and docs contract**

Add `regression-intake.sh` to `SCRIPT_NAMES`, create `regressions/` during beta pack generation, and update generated README order to run `./regression-intake.sh` after `./beta-day-report.sh` when failures are open.

- [x] **Step 5: Verify green**

Run the focused init-beta and docs tests again. Expected: PASS.

### Task 3: Runbooks, Debt, and Final Verification

**Files:**
- Modify: `docs/current/qq-group-chatbot.md`
- Modify: `docs/current/qq-group-chatbot-operations.md`
- Modify: `docs/current/refactoring-debt.md`

- [x] **Step 1: Update runbooks**

Document the closeout order: beta-day-report, regression-intake, inspect replay drafts, then run `qq replay` after filling missing context.

- [x] **Step 2: Update refactoring debt**

Update the Social QQ CLI Runner debt note if `runner.py` remains over 800 lines after this command.

- [x] **Step 3: Final verification**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_runner.py tests/unit/features/social tests/integration/social/test_qq_runtime_wiring.py tests/integration/social/test_social_fake_platform_flow.py tests/unit/integrations/qq/test_onebot_adapter.py tests/unit/integrations/qq/test_onebot_ws_client.py tests/integration/qq/test_fake_onebot_flow.py tests/unit/docs/test_qq_group_chatbot_docs.py -q
git diff --check
```

Expected: tests pass and whitespace check has no output.

### Acceptance Standard

- Operators can run one command after beta day report to create replay drafts for open failures.
- Generated replay drafts use the existing `qq replay` schema.
- Generated beta packs include `regression-intake.sh` and `regressions/`.
- The feature preserves human judgment: it drafts replay cases but does not mark failures closed automatically.
