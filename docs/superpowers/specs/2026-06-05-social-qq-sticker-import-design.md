# QQ Sticker Import Design

## Goal

Let operators build `sticker-library.json` from a local sticker asset directory
instead of hand-writing every sticker entry.

## Scope

This slice adds a `qq import-stickers` CLI command. It does not change sticker
ranking, reply selection, OneBot sending, or replay semantics.

## Input Format

The source directory contains `manifest.json`:

```json
{
  "stickers": [
    {
      "sticker_id": "ship-it",
      "file": "ship.png",
      "tags": ["ship", "review"],
      "meaning": "代码通过时使用",
      "media_ref": "file://ship.png"
    }
  ]
}
```

`media_ref` is optional. If it is missing, the importer writes
`file://<file>`. The file path must be relative to the source directory and must
exist. Each imported entry gets `allowed_groups` from the command `--group`.

## Output

The command writes a normal `StickerLibrary` JSON file, so existing
`apply-profile`, `inspect stickers`, `startup-check`, and replay paths can use
it without a new contract.

## Acceptance

- `qq import-stickers` writes a valid `sticker-library.json` from a local
  manifest and reports imported IDs.
- Missing files, duplicate IDs, empty tags, and invalid manifest shape fail
  before output is written.
- An imported library can replace the generated profile sticker library and
  pass the existing beta check.
- Docs describe the manifest and command in operator terms.
