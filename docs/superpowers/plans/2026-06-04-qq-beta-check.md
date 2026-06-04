# QQ Beta Check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a QQ beta pack check command that verifies a generated pack is runnable, auditable, and still blocks accidental sends.

**Architecture:** Keep pack verification in `src/isotope/features/social/beta_check.py` so `runner.py` remains a CLI dispatcher. The check reads the generated pack, validates config and scripts, runs shell syntax checks, exercises pause/resume/export-log against the pack state, and verifies `send-run.sh` refuses to run without `ISOTOPE_QQ_ENABLE_SEND=1`.

**Tech Stack:** Python 3.13, argparse, pathlib, subprocess, pytest, existing `isotope-social qq` runner.

---

### Task 1: Add Beta Pack Check Behavior

**Files:**
- Create: `src/isotope/features/social/beta_check.py`
- Modify: `src/isotope/features/social/runner.py`
- Test: `tests/unit/features/social/test_social_runner.py`

- [x] **Step 1: Write the failing CLI test**

Add a test that creates a beta pack, runs `qq beta-check`, and asserts the public JSON report includes config checks, script checks, operations checks, and a send guard check.

- [x] **Step 2: Run the new test and verify it fails**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_runner.py::test_social_runner_qq_beta_check_exercises_operator_pack -q
```

Expected: FAIL because `beta-check` is not a registered QQ command.

- [x] **Step 3: Implement `beta_check.py`**

Create `QQBetaCheckConfig`, `QQBetaCheckResult`, and `check_qq_beta_pack(...)`. The checker must:

- require `config.json`, `state/`, `logs/`, and all generated scripts;
- parse `config.json` as JSON;
- run `bash -n` for each script;
- run `pause.sh`, `resume.sh`, and `export-log.sh`;
- run `send-run.sh` without the send environment variable and require exit code `2`;
- return a JSON-safe report with `ok`, `checks`, and `export_log_path`.

- [x] **Step 4: Wire `qq beta-check` into `runner.py`**

Add parser args:

```text
qq beta-check --pack-dir <dir> [--json]
```

The handler calls `check_qq_beta_pack(...)` and returns `{"status": "ok", "command": "beta-check", ...}`.

- [x] **Step 5: Run the focused test and verify it passes**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_runner.py::test_social_runner_qq_beta_check_exercises_operator_pack -q
```

Expected: PASS.

### Task 2: Document Operator Acceptance

**Files:**
- Modify: `docs/current/qq-group-chatbot.md`
- Modify: `docs/current/qq-group-chatbot-operations.md`
- Modify: `tests/unit/docs/test_qq_group_chatbot_docs.py`

- [x] **Step 1: Write the failing docs assertion**

Require the QQ docs to mention `beta-check` and the send guard behavior.

- [x] **Step 2: Run the docs test and verify it fails**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/docs/test_qq_group_chatbot_docs.py -q
```

Expected: FAIL until docs include the new command.

- [x] **Step 3: Update docs**

Document the generated pack acceptance order:

```bash
isotope-social qq beta-check --pack-dir .isotope/qq-beta --json
cd .isotope/qq-beta
./health.sh
./dry-run.sh
ISOTOPE_QQ_ENABLE_SEND=1 ./send-run.sh
./export-log.sh
```

- [x] **Step 4: Run focused verification**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_runner.py tests/unit/docs/test_qq_group_chatbot_docs.py -q
git diff --check
```

Expected: tests pass and `git diff --check` has no output.

### Acceptance Standard

- A generated beta pack can be checked by one command before touching a real QQ group.
- The report says exactly which required files, scripts, operator operations, and send guard checks passed.
- The send script still refuses to send unless `ISOTOPE_QQ_ENABLE_SEND=1` is set.
- Docs teach the operator path in executable commands, not vague prose.
