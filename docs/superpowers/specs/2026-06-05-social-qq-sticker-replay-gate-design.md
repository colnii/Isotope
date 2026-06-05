# QQ Sticker Replay Gate Design

## Goal

Make QQ replay reports prove that sticker behavior is product-ready before a real
group session. The report must show which sticker IDs appeared as candidates,
which sticker IDs were forbidden by the replay, and that dry-run replay did not
select a sticker action for sending.

## Scope

This slice extends replay expectations only. It does not change OneBot, live
send behavior, sticker ranking, or LLM reply generation.

## Design

`qq replay` already runs the fake OneBot path in dry-run and writes
`qq_replay_report`. The new gate reuses the existing `expectations` object and
adds three fields:

- `require_sticker_candidate_ids`: every listed sticker ID must appear in
  proposed candidates.
- `forbid_sticker_candidate_ids`: none of the listed sticker IDs may appear in
  proposed candidates.
- `max_selected_sticker_actions`: the number of selected sticker send actions
  must be less than or equal to this value. The generated replay default is `0`
  because replay is dry-run.

The replay summary will include `sticker_candidate_ids`,
`selected_sticker_ids`, and `selected_sticker_action_count` so operators can see
the concrete IDs, not only counts.

## Acceptance

- Generated `qq init-replay` files include the three new expectation fields.
- A profiled beta replay passes when `ship-it` appears as a candidate and no
  sticker action is selected in dry-run.
- Replay reports fail when a required sticker ID is missing or a forbidden
  sticker ID appears.
- Docs explain the new fields in plain operator terms.
