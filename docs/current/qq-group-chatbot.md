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
    "reply_provider": "deterministic",
    "capability": {
      "enabled": false
    }
  },
  "role_card_path": "tests/fixtures/social/character_cards/qq_helper.json",
  "sticker_library_path": "tests/fixtures/social/stickers/engineering.json"
}
```

Start beta in dry-run, inspect decisions, then enable sends only for the
controlled group.

Enable social capability calls only for a controlled operator test. Capability
use has two gates: the role card must allow the capability in
`tools.allowed_capabilities`, and `runtime.capability` must explicitly map
group text to one capability. Keep `approval_required` enabled unless the
capability is safe to run from ordinary group messages:

```json
{
  "runtime": {
    "capability": {
      "enabled": true,
      "capability_id": "supervisor.request_context",
      "trigger_keywords": ["capacity"],
      "input_defaults": {
        "cwd": "/path/to/isotope",
        "state_root": ".isotope/qq-capacity"
      },
      "query_input_key": "query",
      "approval_keywords": ["批准"],
      "approval_required": true
    }
  },
  "role_card": {
    "tools": {
      "allowed_capabilities": ["supervisor.request_context"]
    }
  }
}
```

When a matching group message arrives, QQ social proposes a
`call_capability` action. Without an operator approval keyword from a configured
operator, the bot replies with an approval prompt instead of running the
capability. With approval, `SocialCapabilityBridge` calls the configured
capability and sends a low-sensitive result summary back to the group.

You can generate a self-contained beta directory instead of hand-writing the
config and commands:

```bash
isotope-social qq init-beta --output-dir .isotope/qq-beta \
  --group <controlled_group_id> --operator <operator_qq_id> \
  --bot-user-id <bot_qq> --websocket-url ws://127.0.0.1:3001 --json
```

The generated pack contains `config.json`, `state/`, `logs/`, `diagnostics.sh`,
`first-run-rehearsal.sh`, `first-run.sh`, `health.sh`, `startup-check.sh`,
`dry-run.sh`, `review-dry-run.sh`, `import-stickers.sh`,
`beta-day-report.sh`, `record-failure.sh`, `regression-intake.sh`,
`send-run.sh`, `pause.sh`, `resume.sh`, `export-log.sh`, and a `README.md`
with the first-run order. It also creates `sticker-assets/manifest.json`,
`logs/failures.json` for operator failure records, and `regressions/` for
replay drafts.

Generate editable role and sticker files before the first real session:

```bash
isotope-social qq init-profile --output-dir .isotope/qq-profile \
  --group <controlled_group_id> --name 群聊工程猫 --json
isotope-social qq import-stickers \
  --source-dir ./qq-sticker-assets \
  --output .isotope/qq-profile/sticker-library.json \
  --group <controlled_group_id> --pack-id engineering --json
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
`bot_user_id`, `websocket_url`, `runtime.reply_provider`,
`runtime.participation_provider`, LLM provider status when LLM replies or LLM
participation are selected, profile/sticker/replay state, and ordered
`next_steps`. It returns `status: needs_action` until the beta pack is ready.

Before connecting it to a real group session, check the pack itself:

```bash
isotope-social qq beta-check --pack-dir .isotope/qq-beta --json
```

The check validates required files, parses `config.json`, runs shell syntax
checks, exercises `pause.sh`, `resume.sh`, and `export-log.sh`, and confirms
`send-run.sh` still refuses to run unless `ISOTOPE_QQ_ENABLE_SEND=1` is set.
`beta-diagnostics` reports both `replay_report` and
`replay_scenarios_report`; when the scenario report is missing, its
`next_steps` include `create_replay_scenarios` and `run_replay_scenarios`.
For a full local rehearsal before touching OneBot, run
`./first-run-rehearsal.sh` from the generated pack. It creates/applies the
editable profile, runs replay and replay scenarios, then runs startup-check and
diagnostics without calling `health.sh`, `dry-run.sh`, `send-run.sh`, or
`live-run`.
To replace the sample sticker refs with real local files, put the image files
named in `sticker-assets/manifest.json` next to that manifest and run
`./import-stickers.sh`. The script imports the files into
`../qq-profile/sticker-library.json`, applies the profile to the beta pack,
runs replay and replay scenarios, then runs startup-check and diagnostics. If a
file is missing, it stops with the missing path before any OneBot connection is
opened.
For generated packs, `./first-run.sh` runs diagnostics, beta-check,
startup-check, and `./health.sh` in order. It stops with replay commands if
`logs/replay-report.json` or `logs/replay-scenarios-report.json` is missing,
and it never runs `dry-run.sh` or `send-run.sh`.

Create and run a replay before connecting NapCat:

```bash
isotope-social qq init-replay --output .isotope/qq-beta/replay.json \
  --group <controlled_group_id> --bot-user-id <bot_qq> --json
isotope-social qq replay --config-json .isotope/qq-beta/config.json \
  --state-root .isotope/qq-beta/state \
  --replay-json .isotope/qq-beta/replay.json \
  --output .isotope/qq-beta/logs/replay-report.json --json
```

For role-card and sticker-pack tuning, generate scenario replays:

```bash
isotope-social qq init-replay-scenarios \
  --output-dir .isotope/qq-beta/replay-scenarios \
  --group <controlled_group_id> --bot-user-id <bot_qq> --json
```

The pack writes `01-ship-it-candidate.json`,
`02-no-matching-sticker.json`, `03-forbid-frequency-zero.json`, and
`index.json`. Run the full pack with one command against the same beta config:

```bash
isotope-social qq replay-scenarios \
  --config-json .isotope/qq-beta/config.json \
  --state-root .isotope/qq-beta/state \
  --scenario-dir .isotope/qq-beta/replay-scenarios \
  --output .isotope/qq-beta/logs/replay-scenarios-report.json \
  --reports-dir .isotope/qq-beta/logs/replay-scenario-reports --json
```

The command writes `replay-scenarios-report.json` as the aggregate report and
one per-scenario `qq_replay_report` under `replay-scenario-reports`. It exits
with status 2 when any scenario fails, so it can guard startup scripts or CI.
Use these scenarios to prove the expected sticker appears, prove an unmatched
scene reports `no_matching_sticker`, and catch accidental `use_frequency_zero`
role-card settings.

Review `replay-report.json` for proposed actions, selected actions, sticker
candidates, blocked turns, and send feedback count. Replay runs as dry-run and
does not send QQ messages.

Replay files include an `expectations` object. The generated defaults require
two processed events, at least one proposed action, at least one sticker
candidate through `min_sticker_candidates`, the concrete sticker candidate
`ship-it` through `require_sticker_candidate_ids`, no forbidden sticker
candidates through `forbid_sticker_candidate_ids`, no selected sticker action
through `max_selected_sticker_actions`, no send feedback, no sent group
messages, and `require_all_dry_run`. The replay summary exposes
`sticker_candidate_ids`, `selected_sticker_ids`, and
`selected_sticker_action_count` so the operator can inspect actual sticker IDs,
not only counts. Treat `passed: false` in `replay-report.json` or CLI JSON as a
blocker before live dry-run.

Run the startup gate after replay and before generated live scripts:

```bash
isotope-social qq startup-check --pack-dir .isotope/qq-beta \
  --replay-report .isotope/qq-beta/logs/replay-report.json \
  --replay-scenarios-report .isotope/qq-beta/logs/replay-scenarios-report.json \
  --json
```

The result must show `ready: true`. The check names are `beta_pack`,
`profile_assets`, `sticker_assets`, `llm_reply_provider`, `replay_report`, and
`replay_scenarios_report`. A blocked result means the generated `dry-run.sh`
and `send-run.sh` will stop before connecting to OneBot. `llm_reply_provider`
passes without model configuration when `runtime.reply_provider` is
`deterministic`; when it is `llm`, the shared Isotope LLM provider must resolve
successfully.

## Run

NapCat must expose a OneBot 11 WebSocket endpoint. The live path is:

1. OneBot/NapCat emits group events.
2. `OneBotAdapter.normalize_event(...)` converts events to `SocialMessage`.
3. `SocialContextBuilder` combines role card, lorebook, recent messages, and
   memory previews.
4. `SocialDecisionLoop` proposes and selects an action.
5. If `runtime.capability` matches the message, `SocialCapabilityBridge` can
   execute the selected `call_capability` action after approval.
6. `OneBotAdapter.send_action(...)` sends the selected reply or capability
   report.
7. `SocialOperationsController` records decision, send, and capability reports.

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

Longer QQ sessions can also let the LLM decide whether to participate before a
reply is selected. This is opt-in; the default remains rule-based wake behavior
for stable replays and conservative beta starts:

```json
{
  "runtime": {
    "participation_provider": "llm",
    "reply_provider": "llm"
  }
}
```

With `participation_provider = "llm"`, ordinary group messages are passed to the
configured chat provider with the active role card, current chat context, recent
messages, memory previews, lorebook entries, wake signals, and dry-run flag. The
model returns either a `silent` decision or a `reply_text` candidate. System
guards still enforce group allowlists, paused groups, dry-run behavior, send-run
flags, recent-send suppression, duplicate handling, and provider failure
fallbacks. Start this mode in dry-run and inspect the proposed decisions before
enabling sends.

To use Mimo for QQ LLM replies, keep the key in the local gitignored LLM pool
TOML and give the entry an explicit provider name:

```toml
[[agents.providers]]
provider = "mimo"
base_url = "https://token-plan-cn.xiaomimimo.com/v1"
model = "mimo-v2.5-pro"
max_tokens = 2048
api_keys = [
  "env:MIMO_API_KEY",
]
```

Then run QQ commands with `ISOTOPE_LLM_PROVIDER=mimo`. The resolver reads
`ISOTOPE_LLM_POOL_TOML_FILES` first, then `SUPERVISOR_LLM_POOL_TOML_FILES`, and
falls back to the local `src/isotope/features/supervisor/supervisor_llm_pool.toml`
when it exists.

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
actions, `reply_preview`, `sticker_candidate_count`, and `warnings`. For sticker
turns, inspect each candidate's `sticker_selection`: selected sticker candidates
show `sticker_id`, `pack_id`, `media_ref`, `media_source`, `local_path`,
`meaning`, `tags`, `reasons`, `candidate_count`, and `allow_sticker_only`; text
fallback candidates still show `blocked_reasons`, `recent_sticker_ids`,
`emotion`, and `scene_tags`. `ready_for_send` is not permission to send; it is
only a review field. Read the warnings and still enable sends manually.

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

`beta-day-report.json` combines dry-run warnings, audit counts,
`sticker_review`, and `failures.json`. Inspect `open_failure_count`,
`sticker_review_candidate_count`, `sticker_blocked_candidate_count`,
`sticker_review.blocked_reason_counts`, and `next_actions` before continuing.
Open failures and blocked sticker candidates need fixes or operator review
before the next beta session.

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
isotope-social qq init-replay-scenarios \
  --output-dir .isotope/qq-beta/replay-scenarios \
  --group <controlled_group_id> --bot-user-id <bot_qq> --json
isotope-social qq replay-scenarios \
  --config-json .isotope/qq-beta/config.json \
  --state-root .isotope/qq-beta/state \
  --scenario-dir .isotope/qq-beta/replay-scenarios \
  --output .isotope/qq-beta/logs/replay-scenarios-report.json \
  --reports-dir .isotope/qq-beta/logs/replay-scenario-reports --json
isotope-social qq replay --config-json .isotope/qq-beta/config.json \
  --state-root .isotope/qq-beta/state \
  --replay-json .isotope/qq-beta/replay.json \
  --output .isotope/qq-beta/logs/replay-report.json --json
isotope-social qq startup-check --pack-dir .isotope/qq-beta \
  --replay-report .isotope/qq-beta/logs/replay-report.json \
  --replay-scenarios-report .isotope/qq-beta/logs/replay-scenarios-report.json \
  --json
cd .isotope/qq-beta
./first-run-rehearsal.sh
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

Real smoke is a developer setting, not an application setting. Copy the example
TOML once beside the QQ integration test, fill in the local test group and
NapCat values, and keep the real file uncommitted:

```bash
cp tests/integration/qq/qq_real_smoke.toml.example \
  tests/integration/qq/qq_real_smoke.local.toml
```

Fill `tests/integration/qq/qq_real_smoke.local.toml`:

```toml
[qq.real_smoke]
enabled = true
onebot_url = "ws://127.0.0.1:3001"
test_group = "<controlled_group_id>"
bot_user_id = "<bot_qq>"
access_token = ""
mode = "health"
timeout = 3
```

`access_token` is the NapCat OneBot token. Leave it empty when NapCat has no
token. If you do not want the token in TOML, keep it empty and set
`ISOTOPE_QQ_ACCESS_TOKEN` for that one shell. Run health mode with:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/integration/qq/test_fake_onebot_flow.py -q
```

The default `mode` is `health`. It connects to the WebSocket endpoint with
`live-run --max-events 0`, writes a temporary config and state file, and does
not consume group messages.

To consume at most one real group event without sending, use dry-run mode:

```toml
[qq.real_smoke]
mode = "dry-run"
```

Then rerun the same pytest command. `ISOTOPE_QQ_REAL_SMOKE=1`,
`ISOTOPE_QQ_REAL_SMOKE_CONFIG`, `ISOTOPE_QQ_REAL_SMOKE_MODE`,
`ISOTOPE_QQ_ONEBOT_URL`, `ISOTOPE_QQ_TEST_GROUP`, `ISOTOPE_QQ_BOT_USER_ID`,
`ISOTOPE_QQ_ACCESS_TOKEN`, and `ISOTOPE_QQ_REAL_SMOKE_TIMEOUT` remain supported
as temporary overrides for CI or one-off shells. The old
`.isotope/dev/qq-real-smoke.toml` path is still supported as a fallback.
Automated real smoke never passes `--send`; send-enabled beta is the manual
`live-run --send` command above.

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

Sticker entries can be imported from a local asset directory. Put image files
next to a `manifest.json` file:

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

Then write the profile sticker library:

```bash
isotope-social qq import-stickers \
  --source-dir ./qq-sticker-assets \
  --output .isotope/qq-profile/sticker-library.json \
  --group <controlled_group_id> --pack-id engineering --json
```

The importer checks every manifest file path before writing output. If
`media_ref` is omitted, it writes `file://<file>`. It also records `local_path`
relative to `sticker-library.json` so startup-check can verify the asset still
exists after import. The output is a normal `sticker-library.json`, so
`apply-profile`, `inspect stickers`, `startup-check`, and replay use the same
path as a hand-written library.

Generated beta packs also include `sticker-assets/manifest.json` and
`./import-stickers.sh` so the operator can do the same import from inside the
pack:

```bash
cd .isotope/qq-beta
# put ship.png next to sticker-assets/manifest.json, or edit the manifest
./import-stickers.sh
```

That script does the import, applies the profile, reruns replay scenarios, and
finishes with diagnostics. It does not call `live-run`, `health.sh`,
`dry-run.sh`, or `send-run.sh`.

`startup-check` reports sticker `sticker_ids`, replay
`required_sticker_ids`, `missing_required_sticker_ids`, and
`missing_local_paths`. Treat missing local files or missing replay-required
sticker IDs as blockers before any live dry-run.

Sticker entries need stable IDs, pack IDs, media refs, tags, meaning, source,
and group allow/block rules. Example output entry:

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

Role-card `stickers.use_frequency` is the first switch for sticker candidates.
Set it to `0.0` when the role should answer with text only. Any value above
`0.0` allows sticker candidates after emotion or scene tags match. The bot also
checks recent successful sends: after it sends a sticker, the next matching turn
falls back to text instead of proposing another sticker, and the same
`sticker_id` is not repeated from recent send feedback.

Replay reports also explain missing sticker candidates. Check
`summary.sticker_candidate_block_reason_counts` for counts by reason, and each
proposed text candidate's `metadata.sticker_selection.blocked_reasons` for the
turn-level reason. Common reasons are `use_frequency_zero` for text-only sticker
settings, `recent_sticker_feedback` when the bot just sent a sticker, and
`no_matching_sticker` when the current group, emotion, and scene tags did not
match any sticker.

Use replay expectations to prove the pack behaves as intended:

```json
{
  "require_sticker_candidate_ids": ["ship-it"],
  "forbid_sticker_candidate_ids": ["wrong-tone"],
  "require_sticker_block_reasons": [],
  "forbid_sticker_block_reasons": ["use_frequency_zero"],
  "max_selected_sticker_actions": 0
}
```

`require_sticker_candidate_ids` means the listed stickers must appear as
proposed candidates. `forbid_sticker_candidate_ids` means the listed stickers
must not appear. `require_sticker_block_reasons` means the listed missing-sticker
reasons must appear in `sticker_candidate_block_reason_counts`.
`forbid_sticker_block_reasons` means the listed reasons must not appear.
`max_selected_sticker_actions` should stay `0` in replay because replay is a
dry-run and must not choose a send action.
