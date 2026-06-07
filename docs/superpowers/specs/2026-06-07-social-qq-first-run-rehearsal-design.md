# QQ First-Run Rehearsal Design

## Goal

Add a local first-run rehearsal script to generated QQ beta packs.

## Product Standard

Before touching OneBot, the operator should be able to run one local script that
generates the editable profile, applies it, creates replay files, runs replay
and replay scenarios, then proves startup readiness through diagnostics. This
script must not connect to OneBot and must not call `health.sh`, `dry-run.sh`,
`send-run.sh`, or `live-run`.

## Scope

This slice adds `first-run-rehearsal.sh` to generated beta packs. It does not
change live transport, replay expectations, startup-check validation, or the
existing closeout-oriented `operator-rehearsal.sh`.

## Design

Generated beta packs include `first-run-rehearsal.sh`. The script runs:

- `qq init-profile --force` into `../qq-profile` by default
- `qq apply-profile`
- `qq beta-check`
- `qq init-replay`
- `qq replay`
- `qq init-replay-scenarios`
- `qq replay-scenarios`
- `./startup-check.sh`
- `./diagnostics.sh`

It accepts optional shell variables:

- `ISOTOPE_QQ_REHEARSAL_PROFILE_DIR`
- `ISOTOPE_QQ_REHEARSAL_PROFILE_NAME`

The final stdout JSON line is diagnostics, so a local run can assert
`status: ready` and inspect `next_steps` before any network-facing script runs.

## Reuse Audit

Reuse:

- Existing generated CLI commands for profile, replay, replay scenarios,
  startup-check, and diagnostics.
- Existing `first-run.sh` replay command paths.
- Existing `operator-rehearsal.sh` naming convention while keeping a separate
  script for first-run readiness.

Do not reuse:

- `first-run.sh`, because it intentionally calls `health.sh`.
- `operator-rehearsal.sh`, because it exercises dry-run review and closeout
  reports, not first-run readiness.

## Acceptance

- `qq init-beta` writes `first-run-rehearsal.sh`.
- The script contains no `live-run`, `dry-run.sh`, or `send-run.sh`.
- Running it creates profile assets, replay report, scenario pack, scenario
  aggregate report, and returns diagnostics `status: ready`.
- Docs and generated README name the script and its no-OneBot boundary.
