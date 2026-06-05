# QQ Sticker Block Expectations Design

## Goal

Let replay expectations verify why sticker candidates were absent.

## Scope

This slice extends replay expectations only. It does not change sticker
selection, role-card schema, OneBot sending, or startup checks.

## Design

Replay summary already includes `sticker_candidate_block_reason_counts`. Add two
expectation fields:

- `require_sticker_block_reasons`: every listed reason must appear in the
  summary.
- `forbid_sticker_block_reasons`: none of the listed reasons may appear.

The actual value in expectation results is the list of reason keys from
`sticker_candidate_block_reason_counts`. This mirrors existing
`require_sticker_candidate_ids` and `forbid_sticker_candidate_ids`.

## Acceptance

- Generated replay templates include both fields as editable empty lists.
- Replay can pass when the expected block reason appears.
- Replay can fail with clear actual values when a required reason is missing or
  a forbidden reason appears.
- QQ docs explain both fields in plain language.
