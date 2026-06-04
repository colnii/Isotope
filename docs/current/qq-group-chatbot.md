# QQ Group Chatbot

This runbook describes the controlled QQ group chatbot path built on the
platform-neutral social core and the OneBot/NapCat adapter.

## Setup

Use Python 3.13 or newer and install the project test dependencies:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -e ".[test]"
```

Verify the local core without touching QQ:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/features/social tests/integration/social/test_social_fake_platform_flow.py -q
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/integrations/qq/test_onebot_adapter.py tests/integration/qq/test_fake_onebot_flow.py -q
```

The second command includes the real QQ smoke test file, but the real smoke case
is skipped unless `ISOTOPE_QQ_REAL_SMOKE=1`.

## Config

The first real beta should use one controlled QQ group and one bot account.
Keep the runtime config equivalent to this shape:

```json
{
  "platform": "qq",
  "adapter": "onebot",
  "group_policy": {
    "allowed_groups": ["<controlled_group_id>"],
    "blocked_groups": [],
    "operator_user_ids": ["<operator_qq_id>"],
    "paused_groups": [],
    "default_dry_run": true
  },
  "role_card_path": "tests/fixtures/social/character_cards/qq_helper.json",
  "sticker_library_path": "tests/fixtures/social/stickers/engineering.json"
}
```

Start beta in dry-run, inspect decisions, then enable sends only for the
controlled group.

You can generate a self-contained beta directory instead of hand-writing the
config and commands:

```bash
isotope-social qq init-beta --output-dir .isotope/qq-beta \
  --group <controlled_group_id> --operator <operator_qq_id> \
  --bot-user-id <bot_qq> --websocket-url ws://127.0.0.1:3001 --json
```

The generated pack contains `config.json`, `state/`, `logs/`, `health.sh`,
`dry-run.sh`, `send-run.sh`, `pause.sh`, `resume.sh`, `export-log.sh`, and a
`README.md` with the first-run order.

Before connecting it to a real group session, check the pack itself:

```bash
isotope-social qq beta-check --pack-dir .isotope/qq-beta --json
```

The check validates required files, parses `config.json`, runs shell syntax
checks, exercises `pause.sh`, `resume.sh`, and `export-log.sh`, and confirms
`send-run.sh` still refuses to run unless `ISOTOPE_QQ_ENABLE_SEND=1` is set.

## Run

NapCat must expose a OneBot 11 WebSocket endpoint. The live path is:

1. OneBot/NapCat emits group events.
2. `OneBotAdapter.normalize_event(...)` converts events to `SocialMessage`.
3. `SocialContextBuilder` combines role card, lorebook, recent messages, and
   memory previews.
4. `SocialDecisionLoop` proposes and selects an action.
5. `OneBotAdapter.send_action(...)` sends the selected `SocialReplyAction`.
6. `SocialOperationsController` records decision, send, and capability reports.

Check the WebSocket connection without consuming a group event:

```bash
isotope-social qq live-run --config-json config.json --state-root .isotope/qq \
  --websocket-url ws://127.0.0.1:3001 --max-events 0 --json
```

Run a controlled dry-run session. This receives real QQ events and records
decisions, but sends nothing:

```bash
isotope-social qq live-run --config-json config.json --state-root .isotope/qq \
  --websocket-url ws://127.0.0.1:3001 --max-events 10 --json
```

Enable sends only after dry-run decisions are acceptable:

```bash
isotope-social qq live-run --config-json config.json --state-root .isotope/qq \
  --websocket-url ws://127.0.0.1:3001 --max-events 10 --send --json
```

For a generated beta pack, use:

```bash
isotope-social qq beta-check --pack-dir .isotope/qq-beta --json
cd .isotope/qq-beta
./health.sh
./dry-run.sh
ISOTOPE_QQ_ENABLE_SEND=1 ./send-run.sh
./export-log.sh
```

If NapCat has an access token, pass it explicitly:

```bash
isotope-social qq live-run --config-json config.json --state-root .isotope/qq \
  --websocket-url ws://127.0.0.1:3001 --access-token "$ONEBOT_ACCESS_TOKEN" \
  --max-events 10 --json
```

Real smoke must be explicit:

```bash
ISOTOPE_QQ_REAL_SMOKE=1 \
ISOTOPE_QQ_ONEBOT_URL=ws://127.0.0.1:3001 \
ISOTOPE_QQ_TEST_GROUP=<controlled_group_id> \
PYTHONPATH=src .venv/bin/python -m pytest tests/integration/qq/test_fake_onebot_flow.py -q
```

The default real smoke mode is `health`. It connects to the WebSocket endpoint
with `live-run --max-events 0`, writes a temporary config and state file, and
does not consume group messages.

To consume at most one real group event without sending, use dry-run mode:

```bash
ISOTOPE_QQ_REAL_SMOKE=1 \
ISOTOPE_QQ_REAL_SMOKE_MODE=dry-run \
ISOTOPE_QQ_ONEBOT_URL=ws://127.0.0.1:3001 \
ISOTOPE_QQ_TEST_GROUP=<controlled_group_id> \
ISOTOPE_QQ_BOT_USER_ID=<bot_qq> \
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/integration/qq/test_fake_onebot_flow.py::test_real_qq_smoke_is_explicitly_opt_in -q
```

If NapCat requires a token, set `ISOTOPE_QQ_ACCESS_TOKEN`. Automated real smoke
never passes `--send`; send-enabled beta is the manual `live-run --send` command
above.

Do not run real smoke in a public or high-traffic group.

## Role-Card Tuning

Tune role cards by replaying fake platform tests before real sends:

1. Adjust identity, voice, social behavior, tool policy, and sticker preferences.
2. Run `tests/unit/features/social/test_character_card.py`.
3. Run `tests/integration/social/test_social_fake_platform_flow.py`.
4. Inspect why the bot spoke or stayed silent using operations decision logs.
5. Only then test in the controlled group.

The role must stay recognizable across several days. If the bot starts sounding
like a generic assistant, change the card and add a fake-platform regression.

## Sticker Pack Setup

Sticker entries need stable IDs, pack IDs, media refs, tags, meaning, source,
and group allow/block rules. Example:

```json
{
  "sticker_id": "ship-it",
  "pack_id": "engineering",
  "media": {
    "media_ref": "qq-image://ship-it",
    "kind": "sticker",
    "source": "local_pack"
  },
  "tags": ["ship", "review"],
  "meaning": "代码通过时使用",
  "allowed_groups": ["<controlled_group_id>"],
  "source": "engineering_pack"
}
```

A sticker should match emotion or scene tags first; role preferences only rank
already relevant stickers.
