# QQ Group Chatbot Operations

This runbook covers operator actions for a controlled QQ group beta.

## Pause

Pause is group-scoped. Pausing one group must not pause another group.

Python-level control surface:

```python
from isotope.features.social import SocialOperationsController

ops = SocialOperationsController()
ops.pause_group("<group_id>", operator_user_id="<operator_qq_id>")
```

Current CLI surface:

```bash
isotope-social qq pause --config-json config.json --state-root .isotope/qq \
  --group <group_id> --operator <operator_qq_id>
isotope-social qq resume --config-json config.json --state-root .isotope/qq \
  --group <group_id> --operator <operator_qq_id>
```

Only configured operators can pause or resume a group. A non-operator response
must name the rejected user ID.

For a controlled beta, generate the operator pack first:

```bash
isotope-social qq init-beta --output-dir .isotope/qq-beta \
  --group <group_id> --operator <operator_qq_id> \
  --bot-user-id <bot_qq> --websocket-url ws://127.0.0.1:3001 --json
```

The pack writes `health.sh`, `startup-check.sh`, `dry-run.sh`,
`review-dry-run.sh`, `send-run.sh`, `pause.sh`, `resume.sh`, and
`export-log.sh`. Run `send-run.sh` only with `ISOTOPE_QQ_ENABLE_SEND=1`.

Generate an editable profile pack and apply it to the beta pack before checking
or running it:

```bash
isotope-social qq init-profile --output-dir .isotope/qq-profile \
  --group <group_id> --name 群聊工程猫 --json
isotope-social qq apply-profile --pack-dir .isotope/qq-beta \
  --profile-dir .isotope/qq-profile --json
```

The profile directory contains `role-card.json` and `sticker-library.json`.
`apply-profile` updates `.isotope/qq-beta/config.json` to read those files and
writes `.isotope/qq-beta/config.before-profile.json` as the previous config.

Before the first live session, run the pack check:

```bash
isotope-social qq beta-check --pack-dir .isotope/qq-beta --json
```

The check verifies the pack files, script syntax, pause/resume/export-log
commands, and the `send-run.sh` guard that refuses to send without
`ISOTOPE_QQ_ENABLE_SEND=1`.

Run a replay before connecting to the real group:

```bash
isotope-social qq init-replay --output .isotope/qq-beta/replay.json \
  --group <group_id> --bot-user-id <bot_qq> --json
isotope-social qq replay --config-json .isotope/qq-beta/config.json \
  --state-root .isotope/qq-beta/state \
  --replay-json .isotope/qq-beta/replay.json \
  --output .isotope/qq-beta/logs/replay-report.json --json
```

Open `replay-report.json` and check whether the role sounds like the intended
group member, whether sticker candidates match the scene, and whether the bot
stays silent when it should. Replay is dry-run and must not send QQ messages.
The generated replay file has an `expectations` section with rules such as
`min_sticker_candidates`, `max_send_feedback`, and `require_all_dry_run`.
`qq replay` writes `passed` plus each rule result. Do not continue to live
dry-run while `passed` is `false`.

Run the startup gate after replay:

```bash
isotope-social qq startup-check --pack-dir .isotope/qq-beta \
  --replay-report .isotope/qq-beta/logs/replay-report.json --json
```

`ready` must be `true`. The checks are `beta_pack`, `profile_assets`,
`sticker_assets`, and `replay_report`. If `profile_assets` fails, apply the
profile pack again. If `replay_report` fails, fix the replay result before
connecting to OneBot. Generated `dry-run.sh` and `send-run.sh` run
`startup-check.sh` before the live command.

## Inspect

Inspect before enabling real sends:

```python
ops.inspect_role(character_card)
ops.inspect_lorebook(lorebook)
ops.inspect_stickers(sticker_library)
ops.health_check(adapter_states=(adapter.connection_state().to_public_dict(),))
```

Current CLI surface:

```bash
isotope-social qq init-profile --output-dir .isotope/qq-profile \
  --group <group_id> --name 群聊工程猫 --json
isotope-social qq apply-profile --pack-dir .isotope/qq-beta \
  --profile-dir .isotope/qq-profile --json
isotope-social qq beta-check --pack-dir .isotope/qq-beta --json
isotope-social qq init-replay --output .isotope/qq-beta/replay.json \
  --group <group_id> --bot-user-id <bot_qq> --json
isotope-social qq replay --config-json .isotope/qq-beta/config.json \
  --state-root .isotope/qq-beta/state \
  --replay-json .isotope/qq-beta/replay.json \
  --output .isotope/qq-beta/logs/replay-report.json --json
isotope-social qq startup-check --pack-dir .isotope/qq-beta \
  --replay-report .isotope/qq-beta/logs/replay-report.json --json
isotope-social qq review-dry-run --state-root .isotope/qq-beta/state \
  --group <group_id> --output .isotope/qq-beta/logs/dry-run-review.json --json
isotope-social qq inspect role --config-json config.json
isotope-social qq inspect lorebook --config-json config.json
isotope-social qq inspect stickers --config-json config.json
isotope-social qq health --config-json config.json --state-root .isotope/qq
isotope-social qq live-run --config-json config.json --state-root .isotope/qq \
  --websocket-url ws://127.0.0.1:3001 --max-events 0 --json
```

Inspect output must answer:

- which role card is active;
- which lorebook entries can enter context;
- which sticker packs and group rules are active;
- whether the adapter is connected;
- how many decision/send/capability log entries exist.

## Shutdown

Use shutdown when the bot misbehaves, the adapter is unstable, or the group no
longer expects bot participation.

1. Pause the group.
2. Stop the OneBot/NapCat connection.
3. Save decision, send, and capability logs.
4. Record any observed failure in the Failure Log.
5. Add or update a regression test before resuming.

Current CLI surface:

```bash
isotope-social qq pause --config-json config.json --state-root .isotope/qq \
  --group <group_id> --operator <operator_qq_id>
isotope-social qq export-log --state-root .isotope/qq \
  --group <group_id> --output artifacts/qq/<date>.json
```

There is no separate shutdown command yet. Shutdown means pausing the group,
stopping the OneBot/NapCat process, exporting logs, and fixing any observed
failure before resuming.

## Dry-Run Review

Dry-run mode returns proposed actions without sending:

```bash
isotope-social qq dry-run --config-json config.json --state-root .isotope/qq \
  --event-json onebot-event.json --json
isotope-social qq live-run --config-json config.json --state-root .isotope/qq \
  --websocket-url ws://127.0.0.1:3001 --max-events 10 --json
```

After dry-run, write the review report:

```bash
isotope-social qq review-dry-run --state-root .isotope/qq \
  --group <group_id> --output .isotope/qq/dry-run-review.json --json
```

Before enabling sends, review:

- wake reason;
- selected or rejected candidates;
- sticker selection reasons;
- `dry-run-review.json` summary, `sticker_candidate_count`, and `warnings`;
- capability reports;
- whether send feedback from a previous turn suppresses repeated replies.

`ready_for_send` in the review report is a report field, not a send permit. Real
sends still require the operator to inspect warnings and manually set
`ISOTOPE_QQ_ENABLE_SEND=1`.

To enable real sends in the controlled group, use the same live command with
`--send`:

```bash
isotope-social qq live-run --config-json config.json --state-root .isotope/qq \
  --websocket-url ws://127.0.0.1:3001 --max-events 10 --send --json
```

## Failure Log

No real beta failures are recorded yet in this branch. Once beta starts, each
failure entry must use this format:

```text
Date:
Group:
Symptom:
Observed input:
Decision log entry:
Send or capability log entry:
Root cause:
Fix:
Regression test:
```

Every real beta bug needs a regression test before the failure is closed. Good
regression locations:

- `tests/integration/social/test_social_fake_platform_flow.py`
- `tests/unit/integrations/qq/test_onebot_adapter.py`
- `tests/integration/qq/test_fake_onebot_flow.py`
- `tests/unit/features/social/test_social_operations.py`

## Multi-Day Checklist

Run this checklist for each controlled beta day:

- Confirm the bot is in the intended group only.
- If starting from a fresh directory, generate the beta pack with `qq init-beta`.
- Generate or update the editable profile with `qq init-profile`.
- Apply the profile with `qq apply-profile`.
- Confirm `allowed_groups` and `operator_user_ids`.
- Run `isotope-social qq beta-check --pack-dir .isotope/qq-beta --json`.
- Run `qq init-replay` and `qq replay`, then review `replay-report.json`.
- Run `qq startup-check` and require `ready: true`.
- Run `./health.sh` before consuming messages.
- Start in dry-run and review at least five representative messages.
- Run `qq review-dry-run` or `./review-dry-run.sh` and inspect warnings.
- Enable sends only after dry-run decisions look correct.
- Check health and adapter state at least once per session.
- Inspect role card and sticker library after any config change.
- Confirm no duplicate message IDs created duplicate replies.
- Confirm send failures appear in logs.
- Pause immediately if the bot sends irrelevant or repeated replies.
- Add regression tests for any real failure before the next beta session.

## Real Smoke Guard

Real QQ smoke is opt-in:

```bash
ISOTOPE_QQ_REAL_SMOKE=1 \
ISOTOPE_QQ_ONEBOT_URL=ws://127.0.0.1:3001 \
ISOTOPE_QQ_TEST_GROUP=<controlled_group_id> \
PYTHONPATH=src .venv/bin/python -m pytest tests/integration/qq/test_fake_onebot_flow.py -q
```

If `ISOTOPE_QQ_REAL_SMOKE` is not `1`, real QQ smoke must stay skipped.
The default mode is health-only and uses `live-run --max-events 0`.

Use dry-run mode to consume at most one real event without sending:

```bash
ISOTOPE_QQ_REAL_SMOKE=1 \
ISOTOPE_QQ_REAL_SMOKE_MODE=dry-run \
ISOTOPE_QQ_ONEBOT_URL=ws://127.0.0.1:3001 \
ISOTOPE_QQ_TEST_GROUP=<controlled_group_id> \
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/integration/qq/test_fake_onebot_flow.py::test_real_qq_smoke_is_explicitly_opt_in -q
```

Automated real smoke must not send messages. Use the manual `live-run --send`
command only after reviewing dry-run decisions.
