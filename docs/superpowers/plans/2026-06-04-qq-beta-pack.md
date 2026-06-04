# QQ Beta Pack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate a controlled QQ beta directory with config, state/log folders, and runnable scripts for health, dry-run, manual send, pause/resume, and log export.

**Architecture:** Keep pack generation in `src/isotope/features/social/beta_pack.py` so `runner.py` remains a thin CLI dispatcher. The generated pack reuses existing `isotope-social qq live-run`, `pause`, `resume`, and `export-log` commands; the send script has an explicit environment-variable guard before `--send` runs.

**Tech Stack:** Python 3.13, argparse, JSON files, POSIX shell scripts, existing QQ social CLI.

---

## Reuse Audit

- Reuse `isotope-social qq live-run` for health/dry-run/send operations.
- Reuse `pause`, `resume`, and `export-log` rather than adding new operation paths.
- Reuse the character-card schema by writing a minimal inline role card in `config.json`.
- Do not create a long-running daemon in this phase; the generated scripts are the operator-facing entry.

## File Structure

- Create `src/isotope/features/social/beta_pack.py`: pack dataclass, config payload, script rendering, file writing.
- Modify `src/isotope/features/social/runner.py`: add `qq init-beta` parser and handler.
- Modify `tests/unit/features/social/test_social_runner.py`: tests for generated pack and overwrite protection.
- Modify `docs/current/qq-group-chatbot.md` and `docs/current/qq-group-chatbot-operations.md`: document `init-beta`.
- Modify `tests/unit/docs/test_qq_group_chatbot_docs.py`: assert docs mention generated beta pack.

## Task 1: CLI Tests

- [ ] **Step 1: Write failing tests**

Add tests proving:

- `qq init-beta` writes `config.json`, `README.md`, `state/`, `logs/`, and six scripts.
- `health.sh` uses `live-run --max-events 0`.
- `dry-run.sh` uses `live-run --max-events <N>` without `--send`.
- `send-run.sh` refuses to run unless `ISOTOPE_QQ_ENABLE_SEND=1`.
- `pause.sh`, `resume.sh`, and `export-log.sh` call the existing commands.
- Running `init-beta` twice without `--force` fails with a clear error.

- [ ] **Step 2: Verify RED**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_runner.py -q
```

Expected: FAIL because `qq init-beta` is not implemented.

## Task 2: Pack Generator

- [ ] **Step 1: Implement `beta_pack.py`**

Create:

- `QQBetaPackConfig`
- `QQBetaPackResult`
- `create_qq_beta_pack(config: QQBetaPackConfig) -> QQBetaPackResult`

The pack must create:

- `config.json`
- `README.md`
- `state/`
- `logs/`
- `health.sh`
- `dry-run.sh`
- `send-run.sh`
- `pause.sh`
- `resume.sh`
- `export-log.sh`

- [ ] **Step 2: Verify unit tests**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_runner.py -q
```

Expected: PASS.

## Task 3: Docs And Regression

- [ ] **Step 1: Update docs**

Document the generated pack command and first-run order:

1. `health.sh`
2. `dry-run.sh`
3. review `logs/` and state
4. `ISOTOPE_QQ_ENABLE_SEND=1 ./send-run.sh`
5. `pause.sh` / `export-log.sh` if behavior is wrong

- [ ] **Step 2: Run selected regression**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_runner.py tests/unit/features/social tests/integration/social/test_qq_runtime_wiring.py tests/integration/social/test_social_fake_platform_flow.py tests/unit/integrations/qq/test_onebot_adapter.py tests/unit/integrations/qq/test_onebot_ws_client.py tests/integration/qq/test_fake_onebot_flow.py tests/unit/docs/test_qq_group_chatbot_docs.py -q
```

Expected: all selected tests pass, real QQ smoke skipped unless opted in.

- [ ] **Step 3: Run diff hygiene**

Run:

```bash
git diff --check
```

Expected: no output.

## Product Acceptance

- [ ] A controlled group operator can create a self-contained beta directory from one command.
- [ ] The generated dry-run and health scripts cannot send messages.
- [ ] The generated send script requires an explicit `ISOTOPE_QQ_ENABLE_SEND=1` confirmation.
- [ ] The generated config allowlists exactly one group by default.
- [ ] The generated README gives a clear first-run order and shutdown path.
