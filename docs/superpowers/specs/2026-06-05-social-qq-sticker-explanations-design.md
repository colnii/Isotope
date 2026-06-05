# QQ Sticker Explanation Design

## Goal

Make replay reports explain why sticker candidates were not proposed.

## Scope

This slice changes sticker candidate metadata and replay summaries. It does not
change OneBot sending, profile import, startup checks, or the role-card schema.

## Design

`StickerLibrary` will expose a selection outcome that contains either the chosen
sticker or a short list of reason codes. Existing `select()` keeps returning only
the chosen sticker for callers that do not need diagnostics.

`SocialDecisionLoop` will use the outcome. When no sticker candidate survives
and the loop falls back to text, the text candidate metadata will include a
`sticker_selection` object with:

- `selected: false`
- `blocked_reasons`
- the request emotion, scene tags, and recent sticker IDs

Replay summary will aggregate `blocked_reasons` from proposed candidates into
`sticker_candidate_block_reason_counts`, so operators can see why sticker
candidates are absent or lower than expected.

## Reason Codes

- `stickers_disabled`: the role card disabled stickers.
- `use_frequency_zero`: the role card set `stickers.use_frequency` to `0.0`.
- `recent_sticker_feedback`: recent successful send feedback already contains a
  sticker.
- `no_matching_sticker`: no sticker matched the current group, emotion, and
  scene tags.

## Acceptance

- Unit tests prove zero frequency and recent sticker feedback produce metadata
  reasons on the text fallback candidate.
- Replay reports include aggregated sticker block reason counts.
- Existing successful sticker candidate reports still include sticker IDs.
- QQ docs explain the new report fields in plain language.
