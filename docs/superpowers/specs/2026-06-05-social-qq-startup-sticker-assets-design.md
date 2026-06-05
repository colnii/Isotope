# QQ Startup Sticker Assets Design

## Goal

Make `qq startup-check` catch broken sticker assets before the bot connects to
OneBot.

## Scope

This slice strengthens existing startup checks. It does not change sticker
ranking, reply generation, replay execution, or OneBot sending.

## Design

`import-stickers` will write `media.local_path` relative to the generated
`sticker-library.json` file. `startup-check` will resolve every non-empty
`local_path` against the sticker library directory and fail `sticker_assets` if
any referenced file is missing.

`startup-check` will also read `require_sticker_candidate_ids` from the replay
report expectations and compare those IDs against the applied sticker library.
If the replay says `ship-it` is required but the library no longer contains
`ship-it`, startup is blocked even if an old replay report still says passed.

## Acceptance

- Imported sticker libraries keep `local_path` usable from the profile
  directory.
- Startup check fails when a sticker `local_path` file is missing.
- Startup check fails when replay-required sticker IDs are missing from the
  applied sticker library.
- Existing generated profile packs without `local_path` keep passing.
