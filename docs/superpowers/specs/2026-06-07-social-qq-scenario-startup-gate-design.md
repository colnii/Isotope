# QQ Replay Scenarios Startup Gate Design

## Goal

Make QQ beta startup require the replay scenario pack result before any script
connects to OneBot.

## Product Standard

The operator should not be able to pass first-run checks with only one replay
report while the sticker tuning scenario pack is missing or failing. The beta
pack must stop before `health.sh`, `dry-run.sh`, or `send-run.sh` can connect.

## Scope

This slice connects existing `qq replay-scenarios` output to startup readiness.
It does not change replay execution, sticker selection, OneBot transport, or
role-card schema.

## Design

Add optional `--replay-scenarios-report` to `qq startup-check`. When provided,
startup-check validates:

- `kind` is `qq_replay_scenarios_report`
- top-level `passed` is true
- `summary.scenario_count` is greater than zero
- `summary.failed_count` is zero
- `summary.passed_count` equals `summary.scenario_count`
- every listed scenario has `passed: true`

Generated beta packs always pass
`--replay-scenarios-report logs/replay-scenarios-report.json` from
`startup-check.sh`. `first-run.sh` checks for
`logs/replay-scenarios-report.json` before `./startup-check.sh` and prints the
exact `init-replay-scenarios` and `replay-scenarios` commands when it is
missing.

## Reuse Audit

Reuse:

- Existing startup gate check tuple and public result shape.
- Existing beta pack script generation helpers and shell command style.
- Existing `qq_replay_scenarios_report` aggregate report contract.

Do not reuse:

- Per-scenario `qq_replay_report` parsing inside startup gate; the aggregate
  report already carries the gate-level pass/fail state.

## Acceptance

- `qq startup-check --replay-scenarios-report ...` passes with a valid aggregate
  report.
- The same command returns exit code 2 when the aggregate report fails.
- Generated `startup-check.sh` includes `--replay-scenarios-report`.
- Generated `first-run.sh` stops before health when the scenario report is
  missing and prints the scenario generation/replay commands.
- Docs and generated README explain the scenario startup gate.
