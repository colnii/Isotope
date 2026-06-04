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
  "websocket_url": "ws://127.0.0.1:3001",
  "group_policy": {
    "allowed_groups": ["<controlled_group_id>"],
    "blocked_groups": [],
    "operator_user_ids": ["<operator_qq_id>"],
    "paused_groups": [],
    "default_dry_run": true
  },
  "runtime": {
    "reply_provider": "deterministic"
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

The generated pack contains `config.json`, `state/`, `logs/`, `diagnostics.sh`,
`first-run.sh`, `health.sh`, `startup-check.sh`, `dry-run.sh`,
`review-dry-run.sh`, `beta-day-report.sh`, `record-failure.sh`,
`regression-intake.sh`, `send-run.sh`, `pause.sh`, `resume.sh`,
`export-log.sh`, and a `README.md` with the first-run order. It also creates
`logs/failures.json` for operator failure records and `regressions/` for replay
drafts.

Generate editable role and sticker files before the first real session:

```bash
isotope-social qq init-profile --output-dir .isotope/qq-profile \
  --group <controlled_group_id> --name 群聊工程猫 --json
isotope-social qq apply-profile --pack-dir .isotope/qq-beta \
  --profile-dir .isotope/qq-profile --json
```

The profile pack writes `role-card.json`, `sticker-library.json`, and
`README.md`. Edit `role-card.json` for identity, voice, group behavior, memory
policy, and tool style. Edit `sticker-library.json` for sticker IDs, media refs,
tags, and meanings.

Run a no-network diagnostics summary whenever the pack changes:

```bash
isotope-social qq beta-diagnostics --pack-dir .isotope/qq-beta --json
```

For generated packs, the same check is available inside the pack:

```bash
cd .isotope/qq-beta
./diagnostics.sh
```

The diagnostics output reports `allowed_groups`, `operator_user_ids`,
`bot_user_id`, `websocket_url`, `runtime.reply_provider`, LLM provider status
when LLM replies are selected, profile/sticker/replay state, and ordered
`next_steps`. It returns `status: needs_action` until the beta pack is ready.

Before connecting it to a real group session, check the pack itself:

```bash
isotope-social qq beta-check --pack-dir .isotope/qq-beta --json
```

The check validates required files, parses `config.json`, runs shell syntax
checks, exercises `pause.sh`, `resume.sh`, and `export-log.sh`, and confirms
`send-run.sh` still refuses to run unless `ISOTOPE_QQ_ENABLE_SEND=1` is set.
For generated packs, `./first-run.sh` runs diagnostics, beta-check,
startup-check, and `./health.sh` in order. It stops with replay commands if
`logs/replay-report.json` is missing, and it never runs `dry-run.sh` or
`send-run.sh`.

Create and run a replay before connecting NapCat:

```bash
isotope-social qq init-replay --output .isotope/qq-beta/replay.json \
  --group <controlled_group_id> --bot-user-id <bot_qq> --json
isotope-social qq replay --config-json .isotope/qq-beta/config.json \
  --state-root .isotope/qq-beta/state \
  --replay-json .isotope/qq-beta/replay.json \
  --output .isotope/qq-beta/logs/replay-report.json --json
```

Review `replay-report.json` for proposed actions, selected actions, sticker
candidates, blocked turns, and send feedback count. Replay runs as dry-run and
does not send QQ messages.

Replay files include an `expectations` object. The generated defaults require
two processed events, at least one proposed action, at least one sticker
candidate through `min_sticker_candidates`, no send feedback, no sent group
messages, and `require_all_dry_run`. Treat `passed: false` in
`replay-report.json` or CLI JSON as a blocker before live dry-run.

Run the startup gate after replay and before generated live scripts:

```bash
isotope-social qq startup-check --pack-dir .isotope/qq-beta \
  --replay-report .isotope/qq-beta/logs/replay-report.json --json
```

The result must show `ready: true`. The check names are `beta_pack`,
`profile_assets`, `sticker_assets`, `llm_reply_provider`, and
`replay_report`. A blocked result means the generated `dry-run.sh` and
`send-run.sh` will stop before connecting to OneBot. `llm_reply_provider` passes
without model configuration when `runtime.reply_provider` is `deterministic`;
when it is `llm`, the shared Isotope LLM provider must resolve successfully.

## Run

NapCat must expose a OneBot 11 WebSocket endpoint. The live path is:

1. OneBot/NapCat emits group events.
2. `OneBotAdapter.normalize_event(...)` converts events to `SocialMessage`.
3. `SocialContextBuilder` combines role card, lorebook, recent messages, and
   memory previews.
4. `SocialDecisionLoop` proposes and selects an action.
5. `OneBotAdapter.send_action(...)` sends the selected `SocialReplyAction`.
6. `SocialOperationsController` records decision, send, and capability reports.

Each dry-run, replay, and live-run turn includes inspectable context. Check
`turn.context.persona_instructions` to confirm the active role card identity,
voice, group behavior, sticker preference, tool style, and memory policy. Check
`turn.context.chat_context` to confirm the readable current group message,
recent messages, memory previews, and selected lorebook entries. QQ mentions
remain structured in `current_message.mentions` and `current_message.parts`;
`current_message.text` is the readable text segment content, not the raw CQ
string.

Text replies are generated through a reply provider. The default provider is
deterministic and keeps replay output stable. To use the configured LLM chat
provider for text replies, add this to `config.json`:

```json
{
  "runtime": {
    "reply_provider": "llm"
  }
}
```

The LLM path uses `turn.context.persona_instructions` and
`turn.context.chat_context`, and requires the model to return JSON with a
non-empty `text` field. If the configured LLM provider is missing or invalid,
the command stops with an explicit configuration error.

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

Write an operator review report from those dry-run decisions:

```bash
isotope-social qq review-dry-run --state-root .isotope/qq \
  --group <controlled_group_id> --output .isotope/qq/dry-run-review.json --json
```

The report writes `ready_for_send`, `summary`, per-turn proposed and rejected
actions, `sticker_candidate_count`, and `warnings`. `ready_for_send` is not
permission to send; it is only a review field. Read the warnings and still
enable sends manually.

Export the audit log, record observed failures, and close the beta day with a
daily report:

```bash
isotope-social qq export-log --state-root .isotope/qq \
  --group <controlled_group_id> --output .isotope/qq/qq-<controlled_group_id>.json --json
isotope-social qq record-failure \
  --failures-json .isotope/qq/failures.json \
  --date 2026-06-04 --group <controlled_group_id> \
  --symptom "表情包过度热情" \
  --observed-input "这能发吗" --json
isotope-social qq beta-day-report --date 2026-06-04 \
  --group <controlled_group_id> \
  --dry-run-review .isotope/qq/dry-run-review.json \
  --export-log .isotope/qq/qq-<controlled_group_id>.json \
  --failures-json .isotope/qq/failures.json \
  --output .isotope/qq/beta-day-report.json --json
```

`beta-day-report.json` combines dry-run warnings, audit counts, and
`failures.json`. Inspect `open_failure_count` and `next_actions` before
continuing. Open failures need fixes and regression tests before the next beta
session.

Create replay drafts for open failures:

```bash
isotope-social qq regression-intake --group <controlled_group_id> \
  --bot-user-id <bot_qq> \
  --failures-json .isotope/qq/failures.json \
  --output-dir .isotope/qq/regressions \
  --index-output .isotope/qq/regression-intake.json --json
```

`regression-intake.json` lists the generated files under `regressions/`. These
files use the same `isotope.qq_replay.v1` format as `qq replay`. Review and edit
the draft event until it reproduces the failure, then run it through `qq replay`
and turn the stable case into a regression test.

Enable sends only after dry-run decisions are acceptable:

```bash
isotope-social qq live-run --config-json config.json --state-root .isotope/qq \
  --websocket-url ws://127.0.0.1:3001 --max-events 10 --send --json
```

For a generated beta pack, use:

```bash
isotope-social qq init-profile --output-dir .isotope/qq-profile \
  --group <controlled_group_id> --name 群聊工程猫 --json
isotope-social qq apply-profile --pack-dir .isotope/qq-beta \
  --profile-dir .isotope/qq-profile --json
isotope-social qq beta-check --pack-dir .isotope/qq-beta --json
isotope-social qq init-replay --output .isotope/qq-beta/replay.json \
  --group <controlled_group_id> --bot-user-id <bot_qq> --json
isotope-social qq replay --config-json .isotope/qq-beta/config.json \
  --state-root .isotope/qq-beta/state \
  --replay-json .isotope/qq-beta/replay.json \
  --output .isotope/qq-beta/logs/replay-report.json --json
isotope-social qq startup-check --pack-dir .isotope/qq-beta \
  --replay-report .isotope/qq-beta/logs/replay-report.json --json
cd .isotope/qq-beta
./first-run.sh
./dry-run.sh
./review-dry-run.sh
./export-log.sh
./record-failure.sh "表情包过度热情" "这能发吗"
./beta-day-report.sh
./regression-intake.sh
ISOTOPE_QQ_ENABLE_SEND=1 ./send-run.sh
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
