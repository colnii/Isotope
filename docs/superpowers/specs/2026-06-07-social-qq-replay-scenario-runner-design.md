# QQ Replay Scenario Runner Design

## Goal

Make generated QQ replay scenario packs runnable as one operator command.

## Product Standard

The operator should not manually copy three `qq replay` commands and then read
three separate reports to know whether sticker tuning is safe. The command must
produce one aggregate answer, keep the per-scenario evidence, and fail loudly
when any expectation fails.

## Scope

This slice adds batch execution for an existing `qq init-replay-scenarios` pack.
It does not change role-card schema, sticker matching, OneBot transport, or
runtime decision policy.

## Design

Add `qq replay-scenarios` with:

- `--config-json`
- `--state-root`
- `--scenario-dir`
- `--output`
- optional `--reports-dir`
- `--json`

The command reads `index.json`, resolves each scenario replay file, and runs
the existing `qq replay` execution path for each scenario. It writes:

- one aggregate `qq_replay_scenarios_report`
- one normal `qq_replay_report` per scenario

The aggregate report includes scenario count, passed count, failed count,
per-scenario replay path, report path, expectations, and summary. When any
scenario fails, the CLI returns exit code 2 and `status: failed`.

## Reuse Audit

Reuse:

- `run_qq_replay` extracted from the existing `qq replay` handler, so runtime
  event processing and expectation evaluation stay single-sourced.
- Existing `qq_runner.py` command registration and `qq_handlers.py` dispatch.
- Existing `qq_replay_scenarios` index format.

Do not reuse:

- Shell command strings from `index.json`; the batch runner should call Python
  code directly, so paths and failure semantics are controlled.

## Acceptance

- `qq replay-scenarios` runs all generated scenario files.
- Passing packs return 0 and write aggregate plus per-scenario reports.
- Failing packs return 2 and name failed scenarios in JSON output.
- Docs show the command, aggregate report, and report directory.
- Relevant social/QQ tests pass.
