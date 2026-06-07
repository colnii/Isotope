# QQ Diagnostics Replay Scenarios Design

## Goal

Make `qq beta-diagnostics` report replay scenario readiness before it tells the
operator to run health or live dry-run scripts.

## Product Standard

Diagnostics should be the operator's first readable checklist. If the replay
scenario aggregate report is missing or failing, diagnostics must say that in
plain JSON and give exact commands to fix it. It must not report `ready` while
`first-run.sh` would still stop on the missing scenario report.

## Scope

This slice updates diagnostics only. It does not change replay execution,
startup-check validation rules, beta pack script generation, or OneBot
transport.

## Design

Add `logs/replay-scenarios-report.json` as a default diagnostics input. The
diagnostics summary includes `replay_scenarios_report` with `exists`, `path`,
`passed`, and the aggregate report summary when available.

When `logs/replay-report.json` exists, diagnostics calls
`check_qq_startup_gate` with both the single replay report and the scenario
aggregate report. This reuses startup-check's validation for
`replay_scenarios_report`.

`next_steps` behavior:

- Missing profile still comes first.
- Missing single replay report asks for `init-replay` and `replay`.
- Missing scenario aggregate report asks for `init-replay-scenarios` and
  `replay-scenarios`.
- Missing LLM provider still takes priority over scenario generation when LLM
  mode is selected.
- Failed startup checks include a `startup-check` command with both replay
  report arguments.

## Reuse Audit

Reuse:

- `check_qq_startup_gate` for scenario report validation.
- Existing diagnostics summary and next-step structure.
- Existing generated scenario pack command names and paths.

Do not reuse:

- `first-run.sh` shell text as diagnostics logic; diagnostics should produce
  structured JSON directly.

## Acceptance

- Diagnostics returns `needs_action` when `logs/replay-scenarios-report.json` is
  missing after the single replay report exists.
- Diagnostics returns `needs_action` when the scenario aggregate report failed.
- Diagnostics returns `ready` only when both replay reports pass.
- Docs name `replay_scenarios_report`, `create_replay_scenarios`, and
  `run_replay_scenarios`.
