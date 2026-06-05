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

The pack writes `diagnostics.sh`, `first-run.sh`, `health.sh`,
`startup-check.sh`, `dry-run.sh`, `review-dry-run.sh`, `beta-day-report.sh`,
`record-failure.sh`, `close-failure.sh`, `failure-to-regression.sh`,
`regression-intake.sh`, `send-run.sh`, `pause.sh`,
`resume.sh`, and `export-log.sh`. It also writes `logs/failures.json` and
creates `regressions/`. Run `send-run.sh` only with
`ISOTOPE_QQ_ENABLE_SEND=1`.

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

After any profile or config edit, run diagnostics before touching OneBot:

```bash
isotope-social qq beta-diagnostics --pack-dir .isotope/qq-beta --json
```

For generated packs, the same check is available inside the pack:

```bash
cd .isotope/qq-beta
./diagnostics.sh
```

Diagnostics does not connect to QQ. It summarizes the configured group,
operator, bot user, OneBot URL, `reply_provider`, profile/sticker/replay state,
LLM provider status when needed, and ordered `next_steps` for the operator.
`first-run.sh` then runs diagnostics, beta-check, startup-check, and health in
order. It stops before health if `logs/replay-report.json` is missing, and it
does not run dry-run or send-enabled commands.

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
`sticker_assets`, `llm_reply_provider`, and `replay_report`. If
`profile_assets` fails, apply the profile pack again. If `llm_reply_provider`
fails, either switch the beta config back to `runtime.reply_provider =
"deterministic"` or configure the shared Isotope LLM provider. If
`replay_report` fails, fix the replay result before connecting to OneBot.
Generated `dry-run.sh` and `send-run.sh` run `startup-check.sh` before the live
command.

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
isotope-social qq export-log --state-root .isotope/qq-beta/state \
  --group <group_id> --output .isotope/qq-beta/logs/qq-<group_id>.json --json
isotope-social qq beta-day-report --date 2026-06-04 \
  --group <group_id> \
  --dry-run-review .isotope/qq-beta/logs/dry-run-review.json \
  --export-log .isotope/qq-beta/logs/qq-<group_id>.json \
  --failures-json .isotope/qq-beta/logs/failures.json \
  --output .isotope/qq-beta/logs/beta-day-report.json --json
isotope-social qq regression-intake --group <group_id> \
  --bot-user-id <bot_qq> \
  --failures-json .isotope/qq-beta/logs/failures.json \
  --output-dir .isotope/qq-beta/regressions \
  --index-output .isotope/qq-beta/logs/regression-intake.json --json
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

## Beta Day Report

At the end of each dry-run or send-enabled beta day, export the group audit log,
record any observed failures, then write the daily report:

```bash
isotope-social qq export-log --state-root .isotope/qq-beta/state \
  --group <group_id> --output .isotope/qq-beta/logs/qq-<group_id>.json --json
isotope-social qq record-failure \
  --failures-json .isotope/qq-beta/logs/failures.json \
  --date 2026-06-04 --group <group_id> \
  --symptom "表情包过度热情" \
  --observed-input "这能发吗" --json
isotope-social qq beta-day-report --date 2026-06-04 \
  --group <group_id> \
  --dry-run-review .isotope/qq-beta/logs/dry-run-review.json \
  --export-log .isotope/qq-beta/logs/qq-<group_id>.json \
  --failures-json .isotope/qq-beta/logs/failures.json \
  --output .isotope/qq-beta/logs/beta-day-report.json --json
```

For generated packs, the same flow is:

```bash
./export-log.sh
./record-failure.sh "表情包过度热情" "这能发吗"
./beta-day-report.sh
./regression-intake.sh
```

If the observed issue should immediately become a replay regression draft, use
the generated wrapper instead:

```bash
./failure-to-regression.sh "表情包过度热情" "这能发吗"
```

You can pass the planned regression test path as the third argument:

```bash
./failure-to-regression.sh "表情包过度热情" "这能发吗" \
  "tests/integration/qq/test_fake_onebot_flow.py"
```

It runs `record-failure.sh`, runs `regression-intake.sh`, and prints the next
`qq replay` command(s) for operator review. When a failure has a
`regression_test`, the intake report also includes `pytest_command`, and the
wrapper prints the pytest command to run from the repo root after the replay
captures the failure. It does not connect to OneBot, does not send messages, and
does not run pytest automatically.

`beta-day-report.json` contains `review_warnings`, audit counts,
`open_failure_count`, and `next_actions`. Treat `open_failure_count > 0` as
unfinished product work: fix the behavior, add or update regression tests, then
close the failure entry.

`regression-intake.sh` reads open entries from `logs/failures.json`, writes
replay draft files under `regressions/`, and writes
`logs/regression-intake.json`. It does not close failures. Open each generated
replay draft, fill any missing context from the real logs, then run it with
`qq replay`. Once the replay captures the failure, add or update the matching
pytest case named in the failure's `regression_test`.

After the replay captures the issue and the pytest regression passes, close the
failure explicitly:

```bash
isotope-social qq close-failure \
  --failures-json .isotope/qq-beta/logs/failures.json \
  --group <group_id> \
  --failure qq-failure-1 \
  --resolved-date 2026-06-06 \
  --fix "replay and pytest passed" \
  --regression-test tests/integration/qq/test_fake_onebot_flow.py --json
cd .isotope/qq-beta
ISOTOPE_QQ_CLOSE_FAILURE_DATE=2026-06-06 \
  ./close-failure.sh qq-failure-1 "replay and pytest passed" \
  tests/integration/qq/test_fake_onebot_flow.py
```

`close-failure` first matches `--failure` against a failure `id`. If no id
matches, it matches the exact `symptom` in the requested group. It refuses to
close when no record matches or more than one record matches. The update writes
`status: fixed`, `resolved_date`, `fix`, and keeps the regression test path.

To enable real sends in the controlled group, use the same live command with
`--send`:

```bash
isotope-social qq live-run --config-json config.json --state-root .isotope/qq \
  --websocket-url ws://127.0.0.1:3001 --max-events 10 --send --json
```

## Failure Log

The generated pack initializes `logs/failures.json` as:

```json
{
  "failures": []
}
```

Prefer the CLI or generated script when adding entries:

```bash
isotope-social qq record-failure \
  --failures-json .isotope/qq-beta/logs/failures.json \
  --date 2026-06-04 --group <group_id> \
  --symptom "表情包过度热情" \
  --observed-input "这能发吗" --json
cd .isotope/qq-beta
./record-failure.sh "表情包过度热情" "这能发吗"
./failure-to-regression.sh "表情包过度热情" "这能发吗" \
  "tests/integration/qq/test_fake_onebot_flow.py"
```

Each failure entry uses this JSON shape:

```json
{
  "failures": [
    {
      "date": "2026-06-04",
      "group": "<group_id>",
      "status": "open",
      "symptom": "表情包语气太像公告",
      "observed_input": "...",
      "decision_log_entry": "...",
      "send_or_capability_log_entry": "...",
      "root_cause": "...",
      "fix": "...",
      "resolved_date": "2026-06-06",
      "regression_test": "tests/integration/social/test_social_fake_platform_flow.py"
    }
  ]
}
```

If you keep a text note while debugging, preserve these fields:

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

Generated `record-failure.sh` accepts that field as the third positional
argument. The environment variable form is still available:

```bash
ISOTOPE_QQ_FAILURE_REGRESSION_TEST=tests/integration/qq/test_fake_onebot_flow.py \
  ./record-failure.sh "表情包过度热情" "这能发吗"
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
- Run `qq beta-diagnostics` or `./diagnostics.sh` and follow `next_steps`.
- Run `isotope-social qq beta-check --pack-dir .isotope/qq-beta --json`.
- Run `qq init-replay` and `qq replay`, then review `replay-report.json`.
- Run `qq startup-check` or `./first-run.sh` and require `ready: true`.
- Confirm `./first-run.sh` reaches `./health.sh` before consuming messages.
- Start in dry-run and review at least five representative messages.
- Run `qq review-dry-run` or `./review-dry-run.sh` and inspect warnings.
- Run `qq export-log` or `./export-log.sh`.
- Record observed failures with `qq record-failure` or `./record-failure.sh`.
- Run `qq beta-day-report` or `./beta-day-report.sh`.
- Inspect `beta-day-report.json`, especially `open_failure_count` and
  `next_actions`.
- Use `./failure-to-regression.sh` when a new observed failure should become a
  replay draft immediately.
- Run `qq regression-intake` or `./regression-intake.sh` when failures are open.
- Inspect `regression-intake.json` and replay drafts under `regressions/`.
- After replay and pytest pass, close the fixed issue with `qq close-failure` or
  `./close-failure.sh`.
- Enable sends only after dry-run decisions look correct and the report has no
  unresolved failures.
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
