# QQ Replay Scenarios Design

## Goal

Provide a generated replay scenario pack for QQ role-card and sticker-pack
tuning.

## Scope

This slice adds a generator command. It does not change replay execution,
sticker selection, OneBot sending, or role-card schema.

## Design

Add `qq init-replay-scenarios` with `--output-dir`, `--group`, and
`--bot-user-id`. The command writes:

- `01-ship-it-candidate.json`: requires the `ship-it` sticker candidate and
  forbids common sticker block reasons.
- `02-no-matching-sticker.json`: uses unmatched emotion and scene tags, then
  requires `no_matching_sticker`.
- `03-forbid-frequency-zero.json`: fails when `use_frequency_zero` appears.
- `index.json`: lists scenario IDs, file paths, purpose text, and replay
  command templates.

The scenarios reuse the same replay JSON format as `qq init-replay`, so
operators can run them with `qq replay` and existing startup checks.

## Acceptance

- The CLI writes all scenario files and an index.
- Scenario files contain concrete runtime and expectation settings.
- Docs name the command and generated files.
- Existing replay and QQ tests keep passing.
