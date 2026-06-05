# QQ Sticker Cadence Design

## Goal

Make role-card sticker preferences affect real QQ reply decisions, not just
profile metadata.

## Scope

This slice changes sticker candidate generation. It does not change OneBot
sending, sticker importing, replay file format, or startup asset checks.

## Product Rules

`stickers.use_frequency` controls whether sticker candidates are allowed:

- `0.0` means do not propose sticker replies.
- A value greater than `0.0` allows sticker candidates when the message emotion
  or scene tags match the sticker library.

Recent successful sticker sends block immediate sticker reuse. If the bot just
sent a sticker in the same group, the next eligible turn should use text unless
another feature explicitly supplies a different cadence window later. The same
sticker ID must not be proposed again while it is present in recent send
feedback.

These rules are guardrails around candidate generation. They must not prevent
normal text replies when the bot was otherwise woken.

## Design

Extend `StickerSelectionRequest` with recent send feedback. `StickerLibrary`
will filter candidates before ranking:

- skip all sticker candidates when role-card `use_frequency` is `0.0`;
- skip sticker-only candidates after recent successful sticker sends;
- skip sticker entries whose `sticker_id` appears in recent successful sticker
  feedback.

`SocialDecisionLoop` will pass its existing `recent_send_feedback` into sticker
selection. If sticker selection returns no candidate because of cadence rules,
the loop falls back to the normal reply provider and proposes text.

## Acceptance

- Unit tests prove `use_frequency=0.0` blocks sticker selection.
- Unit tests prove a recent successful sticker send prevents repeating the same
  sticker and falls back to text in the decision loop.
- Existing sticker matching, replay, fake-platform, and QQ integration tests
  keep passing.
- QQ documentation explains the frequency and repeat behavior in plain product
  terms.
