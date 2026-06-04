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
isotope-social qq inspect role --config-json config.json
isotope-social qq inspect lorebook --config-json config.json
isotope-social qq inspect stickers --config-json config.json
isotope-social qq health --config-json config.json --state-root .isotope/qq
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
```

Before enabling sends, review:

- wake reason;
- selected or rejected candidates;
- sticker selection reasons;
- capability reports;
- whether send feedback from a previous turn suppresses repeated replies.

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
- Confirm `allowed_groups` and `operator_user_ids`.
- Start in dry-run and review at least five representative messages.
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
ISOTOPE_QQ_ONEBOT_URL=http://127.0.0.1:3000 \
ISOTOPE_QQ_TEST_GROUP=<controlled_group_id> \
PYTHONPATH=src .venv/bin/python -m pytest tests/integration/qq/test_fake_onebot_flow.py -q
```

If `ISOTOPE_QQ_REAL_SMOKE` is not `1`, real QQ smoke must stay skipped.
