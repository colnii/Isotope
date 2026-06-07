"""Generate operator files for a controlled QQ beta."""

from __future__ import annotations

import json
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .beta_pack_support import (
    first_run_rehearsal_command,
    init_replay_command,
    init_replay_scenarios_command,
    import_stickers_command,
    qq_replay_command,
    qq_replay_scenarios_command,
    write_sticker_asset_template,
)

SCRIPT_NAMES = (
    "beta-day-report.sh",
    "beta-closeout.sh",
    "close-failure.sh",
    "diagnostics.sh",
    "first-run-rehearsal.sh",
    "first-run.sh",
    "failure-to-regression.sh",
    "health.sh",
    "import-stickers.sh",
    "operator-rehearsal.sh",
    "startup-check.sh",
    "dry-run.sh",
    "review-dry-run.sh",
    "send-run.sh",
    "pause.sh",
    "record-failure.sh",
    "resume.sh",
    "export-log.sh",
    "regression-intake.sh",
)


@dataclass(frozen=True)
class QQBetaPackConfig:
    output_dir: Path
    group_id: str
    operator_user_id: str
    bot_user_id: str
    websocket_url: str
    max_events: int = 10
    force: bool = False
    access_token_env: str = "ONEBOT_ACCESS_TOKEN"

    def __post_init__(self) -> None:
        _required_text(str(self.output_dir), "output_dir")
        _required_text(self.group_id, "group")
        _required_text(self.operator_user_id, "operator")
        _required_text(self.bot_user_id, "bot_user_id")
        _required_text(self.websocket_url, "websocket_url")
        if isinstance(self.max_events, bool) or not isinstance(self.max_events, int):
            raise ValueError("max-events must be a positive integer")
        if self.max_events <= 0:
            raise ValueError("max-events must be a positive integer")
        _required_text(self.access_token_env, "access_token_env")


@dataclass(frozen=True)
class QQBetaPackResult:
    output_dir: Path
    config_path: Path
    readme_path: Path
    state_dir: Path
    logs_dir: Path
    scripts: tuple[Path, ...]

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "output_dir": str(self.output_dir),
            "config_path": str(self.config_path),
            "readme_path": str(self.readme_path),
            "state_dir": str(self.state_dir),
            "logs_dir": str(self.logs_dir),
            "scripts": [path.name for path in self.scripts],
        }


def create_qq_beta_pack(config: QQBetaPackConfig) -> QQBetaPackResult:
    output_dir = config.output_dir
    if output_dir.exists() and any(output_dir.iterdir()) and not config.force:
        raise ValueError(f"beta pack already exists: {output_dir}; pass --force to overwrite")
    output_dir.mkdir(parents=True, exist_ok=True)
    state_dir = output_dir / "state"
    logs_dir = output_dir / "logs"
    regressions_dir = output_dir / "regressions"
    state_dir.mkdir(exist_ok=True)
    logs_dir.mkdir(exist_ok=True)
    regressions_dir.mkdir(exist_ok=True)
    failures_path = logs_dir / "failures.json"
    if not failures_path.exists():
        failures_path.write_text(
            json.dumps({"failures": []}, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    write_sticker_asset_template(output_dir)

    config_path = output_dir / "config.json"
    config_path.write_text(
        json.dumps(_config_payload(config), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    readme_path = output_dir / "README.md"
    readme_path.write_text(_readme(config), encoding="utf-8")

    scripts = tuple(
        _write_script(output_dir / name, _script_body(name, config))
        for name in SCRIPT_NAMES
    )
    return QQBetaPackResult(
        output_dir=output_dir,
        config_path=config_path,
        readme_path=readme_path,
        state_dir=state_dir,
        logs_dir=logs_dir,
        scripts=scripts,
    )


def _write_script(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)
    return path


def _script_body(name: str, config: QQBetaPackConfig) -> str:
    common = _common_env(config)
    if name == "beta-day-report.sh":
        command = _beta_day_report_command(config)
        return f"{common}\n{command}\n"
    if name == "beta-closeout.sh":
        command = _beta_closeout_command()
        return f"{common}\n{command}\n"
    if name == "close-failure.sh":
        return f"{common}\n{_close_failure_command(config)}"
    if name == "diagnostics.sh":
        command = _diagnostics_command()
        return f"{common}\n{command}\n"
    if name == "first-run-rehearsal.sh":
        command = first_run_rehearsal_command(config)
        return f"{common}\n{command}\n"
    if name == "first-run.sh":
        command = _first_run_command(config)
        return f"{common}\n{command}\n"
    if name == "failure-to-regression.sh":
        command = _failure_to_regression_command()
        return f"{common}\n{command}\n"
    if name == "health.sh":
        command = _live_run_command(config, max_events=0, send=False)
        return f"{common}\n{command}\n"
    if name == "import-stickers.sh":
        command = import_stickers_command(config)
        return f"{common}\n{command}\n"
    if name == "operator-rehearsal.sh":
        command = _operator_rehearsal_command(config)
        return f"{common}\n{command}\n"
    if name == "startup-check.sh":
        command = _startup_check_command()
        return f"{common}\n{command}\n"
    if name == "dry-run.sh":
        command = _live_run_command(config, max_events=config.max_events, send=False)
        return f"{common}\n./startup-check.sh 1>&2\n{command}\n"
    if name == "review-dry-run.sh":
        command = _review_dry_run_command(config)
        return f"{common}\n{command}\n"
    if name == "send-run.sh":
        command = _live_run_command(config, max_events=config.max_events, send=True)
        return (
            f"{common}\n"
            'if [ "${ISOTOPE_QQ_ENABLE_SEND:-}" != "1" ]; then\n'
            '  echo "Refusing to send. Set ISOTOPE_QQ_ENABLE_SEND=1 after reviewing '
            'dry-run output." >&2\n'
            "  exit 2\n"
            "fi\n"
            "./startup-check.sh 1>&2\n"
            f"{command}\n"
        )
    if name == "pause.sh":
        return (
            f"{common}\n"
            "isotope-social qq pause --config-json config.json --state-root state "
            f"--group {shlex.quote(config.group_id)} --operator {shlex.quote(config.operator_user_id)} --json\n"
        )
    if name == "record-failure.sh":
        return f"{common}\n{_record_failure_command(config)}"
    if name == "resume.sh":
        return (
            f"{common}\n"
            "isotope-social qq resume --config-json config.json --state-root state "
            f"--group {shlex.quote(config.group_id)} --operator {shlex.quote(config.operator_user_id)} --json\n"
        )
    if name == "export-log.sh":
        output = f"logs/qq-{config.group_id}.json"
        return (
            f"{common}\n"
            "isotope-social qq export-log --state-root state "
            f"--group {shlex.quote(config.group_id)} --output {shlex.quote(output)} --json\n"
        )
    if name == "regression-intake.sh":
        command = _regression_intake_command(config)
        return f"{common}\n{command}\n"
    raise ValueError(f"unknown beta pack script: {name}")


def _common_env(config: QQBetaPackConfig) -> str:
    return (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'cd "$(dirname "$0")"\n'
        f"ONEBOT_ACCESS_TOKEN=\"${{{config.access_token_env}:-}}\"\n"
    )


def _live_run_command(
    config: QQBetaPackConfig,
    *,
    max_events: int,
    send: bool,
) -> str:
    parts = [
        "isotope-social",
        "qq",
        "live-run",
        "--config-json",
        "config.json",
        "--state-root",
        "state",
        "--websocket-url",
        config.websocket_url,
        "--max-events",
        str(max_events),
        "--json",
    ]
    parts.extend(
        [
            "--access-token",
            '"$ONEBOT_ACCESS_TOKEN"',
        ]
    )
    if send:
        parts.append("--send")
    return " ".join(_quote_command_part(part) for part in parts)


def _startup_check_command() -> str:
    parts = [
        "isotope-social",
        "qq",
        "startup-check",
        "--pack-dir",
        ".",
        "--replay-report",
        "logs/replay-report.json",
        "--replay-scenarios-report",
        "logs/replay-scenarios-report.json",
        "--json",
    ]
    return " ".join(shlex.quote(part) for part in parts)


def _diagnostics_command() -> str:
    parts = [
        "isotope-social",
        "qq",
        "beta-diagnostics",
        "--pack-dir",
        ".",
        "--json",
    ]
    return " ".join(shlex.quote(part) for part in parts)


def _first_run_command(config: QQBetaPackConfig) -> str:
    replay_command = qq_replay_command(config)
    init_scenarios_command = init_replay_scenarios_command(config)
    replay_scenarios_command = qq_replay_scenarios_command()
    return (
        "./diagnostics.sh || true\n"
        "isotope-social qq beta-check --pack-dir . --json\n"
        "if ! [ -f logs/replay-report.json ]; then\n"
        '  echo "Missing logs/replay-report.json. Run these commands before first-run:" >&2\n'
        "  echo "
        f"{shlex.quote(init_replay_command(config))} >&2\n"
        "  echo "
        f"{shlex.quote(replay_command)} >&2\n"
        "  exit 2\n"
        "fi\n"
        "if ! [ -f logs/replay-scenarios-report.json ]; then\n"
        '  echo "Missing logs/replay-scenarios-report.json. '
        'Run these commands before first-run:" >&2\n'
        "  echo "
        f"{shlex.quote(init_scenarios_command)} >&2\n"
        "  echo "
        f"{shlex.quote(replay_scenarios_command)} >&2\n"
        "  exit 2\n"
        "fi\n"
        "./startup-check.sh\n"
        "./health.sh\n"
    )


def _review_dry_run_command(config: QQBetaPackConfig) -> str:
    parts = [
        "isotope-social",
        "qq",
        "review-dry-run",
        "--state-root",
        "state",
        "--group",
        config.group_id,
        "--output",
        "logs/dry-run-review.json",
        "--json",
    ]
    return " ".join(shlex.quote(part) for part in parts)


def _beta_day_report_command(config: QQBetaPackConfig) -> str:
    output = f"logs/qq-{config.group_id}.json"
    parts = [
        "isotope-social",
        "qq",
        "beta-day-report",
        "--date",
        '"${ISOTOPE_QQ_BETA_DATE:-$(date +%F)}"',
        "--group",
        config.group_id,
        "--dry-run-review",
        "logs/dry-run-review.json",
        "--export-log",
        output,
        "--failures-json",
        "logs/failures.json",
        "--output",
        "logs/beta-day-report.json",
        "--json",
    ]
    return " ".join(_quote_command_part(part) for part in parts)


def _beta_closeout_command() -> str:
    parts = [
        "isotope-social",
        "qq",
        "beta-closeout",
        "--beta-day-report",
        "logs/beta-day-report.json",
        "--regression-intake",
        "logs/regression-intake.json",
        "--output",
        "logs/beta-closeout.json",
        "--json",
    ]
    return " ".join(shlex.quote(part) for part in parts)


def _regression_intake_command(config: QQBetaPackConfig) -> str:
    parts = [
        "isotope-social",
        "qq",
        "regression-intake",
        "--group",
        config.group_id,
        "--bot-user-id",
        config.bot_user_id,
        "--failures-json",
        "logs/failures.json",
        "--output-dir",
        "regressions",
        "--index-output",
        "logs/regression-intake.json",
        "--json",
    ]
    return " ".join(shlex.quote(part) for part in parts)


def _failure_to_regression_command() -> str:
    return (
        './record-failure.sh "$@"\n'
        "./regression-intake.sh\n"
        "python3 - <<'PY'\n"
        "import json\n"
        "import shlex\n"
        "import sys\n"
        "from pathlib import Path\n"
        "\n"
        'index_path = Path("logs/regression-intake.json")\n'
        "if not index_path.is_file():\n"
        '    print("Missing logs/regression-intake.json after regression intake.", file=sys.stderr)\n'
        "    raise SystemExit(2)\n"
        "payload = json.loads(index_path.read_text(encoding='utf-8'))\n"
        "drafts = payload.get('drafts', [])\n"
        "if not drafts:\n"
        '    print("No open failure replay drafts were generated.", file=sys.stderr)\n'
        "    raise SystemExit(0)\n"
        'print("Next replay command(s):")\n'
        "for draft in drafts:\n"
        "    if not isinstance(draft, dict):\n"
        "        continue\n"
        "    replay_json = str(draft.get('replay_json', '')).strip()\n"
        "    if not replay_json:\n"
        "        continue\n"
        '    command = "isotope-social qq replay --config-json config.json --state-root state "\n'
        "    command += f\"--replay-json {shlex.quote(replay_json)} \"\n"
        '    command += "--output logs/replay-report.json --json"\n'
        "    print(command)\n"
        "pytest_commands = [\n"
        "    str(draft.get('pytest_command', '')).strip()\n"
        "    for draft in drafts\n"
        "    if isinstance(draft, dict) and str(draft.get('pytest_command', '')).strip()\n"
        "]\n"
        "if pytest_commands:\n"
        '    print("Next pytest command(s):")\n'
        "    for command in pytest_commands:\n"
        "        print(command)\n"
        "PY\n"
    )


def _operator_rehearsal_command(config: QQBetaPackConfig) -> str:
    export_log = f"logs/qq-{config.group_id}.json"
    return (
        'REHEARSAL_DATE="${ISOTOPE_QQ_REHEARSAL_DATE:-$(date +%F)}"\n'
        "./diagnostics.sh > logs/operator-rehearsal-diagnostics.json || true\n"
        "python3 - <<'PY'\n"
        "import json\n"
        "from pathlib import Path\n"
        "\n"
        "logs = Path('logs')\n"
        "logs.mkdir(exist_ok=True)\n"
        "dry_run_review = {\n"
        "    'kind': 'qq_dry_run_review',\n"
        f"    'group_id': {config.group_id!r},\n"
        "    'ready_for_send': True,\n"
        "    'summary': {\n"
        "        'decision_count': 1,\n"
        "        'dry_run_decision_count': 1,\n"
        "        'proposed_action_count': 1,\n"
        "        'selected_action_count': 0,\n"
        "        'rejected_action_count': 1,\n"
        "        'sticker_candidate_count': 0,\n"
        "        'send_feedback_count': 0,\n"
        "    },\n"
        "    'warnings': [],\n"
        "    'turns': [],\n"
        "    'metadata': {'source': 'operator_rehearsal'},\n"
        "}\n"
        "audit_log = {\n"
        "    'entries': [\n"
        "        {\n"
        "            'kind': 'decision',\n"
        f"            'group_id': {config.group_id!r},\n"
        "            'payload': {'source': 'operator_rehearsal'},\n"
        "        }\n"
        "    ]\n"
        "}\n"
        "for path, payload in (\n"
        "    (logs / 'dry-run-review.json', dry_run_review),\n"
        f"    (Path({export_log!r}), audit_log),\n"
        "):\n"
        "    path.write_text(\n"
        "        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),\n"
        "        encoding='utf-8',\n"
        "    )\n"
        "PY\n"
        'ISOTOPE_QQ_FAILURE_DATE="$REHEARSAL_DATE" ./failure-to-regression.sh \\\n'
        '  "operator rehearsal failure" \\\n'
        '  "operator rehearsal message" \\\n'
        '  "tests/integration/qq/test_fake_onebot_flow.py"\n'
        'ISOTOPE_QQ_CLOSE_FAILURE_DATE="$REHEARSAL_DATE" ./close-failure.sh \\\n'
        '  "qq-failure-1" \\\n'
        '  "operator rehearsal passed" \\\n'
        '  "tests/integration/qq/test_fake_onebot_flow.py"\n'
        "./regression-intake.sh\n"
        'ISOTOPE_QQ_BETA_DATE="$REHEARSAL_DATE" ./beta-day-report.sh\n'
        "./beta-closeout.sh\n"
        "python3 - <<'PY'\n"
        "from pathlib import Path\n"
        "print(Path('logs/beta-closeout.json').read_text(encoding='utf-8'))\n"
        "PY\n"
    )


def _record_failure_command(config: QQBetaPackConfig) -> str:
    return (
        'SYMPTOM="${1:-${ISOTOPE_QQ_FAILURE_SYMPTOM:-}}"\n'
        'OBSERVED_INPUT="${2:-${ISOTOPE_QQ_FAILURE_OBSERVED_INPUT:-}}"\n'
        'REGRESSION_TEST="${3:-${ISOTOPE_QQ_FAILURE_REGRESSION_TEST:-}}"\n'
        'if [ -z "$SYMPTOM" ]; then\n'
        '  echo "Usage: ./record-failure.sh <symptom> [observed_input] [regression_test]" >&2\n'
        '  echo "Or set ISOTOPE_QQ_FAILURE_SYMPTOM before running." >&2\n'
        "  exit 2\n"
        "fi\n"
        "args=(\n"
        "  isotope-social qq record-failure\n"
        "  --failures-json logs/failures.json\n"
        f"  --date \"${{ISOTOPE_QQ_FAILURE_DATE:-$(date +%F)}}\"\n"
        f"  --group {shlex.quote(config.group_id)}\n"
        '  --symptom "$SYMPTOM"\n'
        ")\n"
        'if [ -n "$OBSERVED_INPUT" ]; then\n'
        '  args+=(--observed-input "$OBSERVED_INPUT")\n'
        "fi\n"
        'if [ -n "${ISOTOPE_QQ_FAILURE_DECISION_LOG_ENTRY:-}" ]; then\n'
        '  args+=(--decision-log-entry "$ISOTOPE_QQ_FAILURE_DECISION_LOG_ENTRY")\n'
        "fi\n"
        'if [ -n "${ISOTOPE_QQ_FAILURE_SEND_OR_CAPABILITY_LOG_ENTRY:-}" ]; then\n'
        '  args+=(--send-or-capability-log-entry "$ISOTOPE_QQ_FAILURE_SEND_OR_CAPABILITY_LOG_ENTRY")\n'
        "fi\n"
        'if [ -n "${ISOTOPE_QQ_FAILURE_ROOT_CAUSE:-}" ]; then\n'
        '  args+=(--root-cause "$ISOTOPE_QQ_FAILURE_ROOT_CAUSE")\n'
        "fi\n"
        'if [ -n "${ISOTOPE_QQ_FAILURE_FIX:-}" ]; then\n'
        '  args+=(--fix "$ISOTOPE_QQ_FAILURE_FIX")\n'
        "fi\n"
        'if [ -n "$REGRESSION_TEST" ]; then\n'
        '  args+=(--regression-test "$REGRESSION_TEST")\n'
        "fi\n"
        '"${args[@]}" --json\n'
    )


def _close_failure_command(config: QQBetaPackConfig) -> str:
    return (
        'FAILURE="${1:-${ISOTOPE_QQ_CLOSE_FAILURE:-}}"\n'
        'FIX="${2:-${ISOTOPE_QQ_CLOSE_FAILURE_FIX:-}}"\n'
        'REGRESSION_TEST="${3:-${ISOTOPE_QQ_CLOSE_FAILURE_REGRESSION_TEST:-}}"\n'
        'if [ -z "$FAILURE" ] || [ -z "$FIX" ]; then\n'
        '  echo "Usage: ./close-failure.sh <failure_id_or_symptom> <fix> [regression_test]" >&2\n'
        '  echo "Or set ISOTOPE_QQ_CLOSE_FAILURE and ISOTOPE_QQ_CLOSE_FAILURE_FIX." >&2\n'
        "  exit 2\n"
        "fi\n"
        "args=(\n"
        "  isotope-social qq close-failure\n"
        "  --failures-json logs/failures.json\n"
        f"  --group {shlex.quote(config.group_id)}\n"
        '  --failure "$FAILURE"\n'
        f"  --resolved-date \"${{ISOTOPE_QQ_CLOSE_FAILURE_DATE:-$(date +%F)}}\"\n"
        "  --status fixed\n"
        '  --fix "$FIX"\n'
        ")\n"
        'if [ -n "$REGRESSION_TEST" ]; then\n'
        '  args+=(--regression-test "$REGRESSION_TEST")\n'
        "fi\n"
        '"${args[@]}" --json\n'
    )


def _quote_command_part(part: str) -> str:
    if part in {'"$ONEBOT_ACCESS_TOKEN"', '"${ISOTOPE_QQ_BETA_DATE:-$(date +%F)}"'}:
        return part
    return shlex.quote(part)


def _config_payload(config: QQBetaPackConfig) -> dict[str, Any]:
    return {
        "bot_user_id": config.bot_user_id,
        "websocket_url": config.websocket_url,
        "dry_run": True,
        "group_policy": {
            "allowed_groups": [config.group_id],
            "blocked_groups": [],
            "operator_user_ids": [config.operator_user_id],
            "paused_groups": [],
            "default_dry_run": True,
        },
        "runtime": {
            "reply_provider": "deterministic",
        },
        "role_card": _role_card(),
        "sticker_library": {"entries": []},
    }


def _role_card() -> dict[str, Any]:
    return {
        "schema_version": "isotope.character_card_plus.v1",
        "identity": {
            "name": "QQ Beta Bot",
            "aliases": ["bot"],
            "description": "受控 QQ 群 beta 验证角色。",
        },
        "voice": {
            "speaking_style": "简洁、克制、先看上下文",
            "tone": "calm",
            "vocabulary": ["beta", "dry-run", "群聊"],
            "example_messages": ["收到，我先记录这轮 dry-run 结果。"],
            "forbidden_style": "不要像客服机器人，不要刷屏。",
        },
        "social_behavior": {
            "talkativeness": 0.35,
            "interruption_style": "only_when_useful",
            "mention_policy": "always_consider",
            "lurk_policy": "watch_and_wait",
            "disagreement_style": "explain_reason",
            "relationship_policy": "remember_stable_preferences",
        },
        "stickers": {
            "enabled": False,
            "favorite_packs": [],
            "style_tags": [],
            "emotion_map": {},
            "use_frequency": 0.0,
            "allow_sticker_only_reply": False,
            "avoid_tags": [],
        },
        "tools": {
            "allowed_capabilities": [],
            "tool_use_style": "disabled_for_beta_bootstrap",
            "after_tool_result_behavior": "answer_briefly",
        },
        "memory": {
            "remember": [],
            "do_not_remember": ["one-off beta messages"],
            "review_policy": "operator_review_before_memory_writes",
        },
        "groups": {"overrides": {}},
    }


def _readme(config: QQBetaPackConfig) -> str:
    return f"""# QQ Controlled Beta Pack

Group: `{config.group_id}`
Bot user: `{config.bot_user_id}`
OneBot WebSocket: `{config.websocket_url}`

## First run order

1. Run `./first-run-rehearsal.sh` to generate/apply the profile, replay, and
   replay scenario reports without connecting to OneBot.
2. Put real sticker files next to `sticker-assets/manifest.json`, then run
   `./import-stickers.sh` to import, apply, replay, startup-check, and
   diagnostics without connecting to OneBot.
3. Run `./first-run.sh`.
4. Run `./diagnostics.sh` again after config or profile edits.
5. Run `./dry-run.sh`.
6. Run `./review-dry-run.sh` and inspect `logs/dry-run-review.json`.
7. Run `./export-log.sh`.
8. Record observed issues in `logs/failures.json`, or use
   `./failure-to-regression.sh` to record and draft a replay regression in one
   operator step.
9. Run `./beta-day-report.sh` and inspect `logs/beta-day-report.json`.
10. Run `./regression-intake.sh` for open failures and inspect `regressions/`
    if you did not already use `./failure-to-regression.sh`.
11. To rehearse the local operator closeout chain without connecting to OneBot,
    run `./operator-rehearsal.sh` and inspect `logs/beta-closeout.json`.
12. Only after dry-run behavior is acceptable, run:

```bash
ISOTOPE_QQ_ENABLE_SEND=1 ./send-run.sh
```

## Stop and inspect

- Pause the group with `./pause.sh`.
- Resume with `./resume.sh` only after the issue is understood.
- Export the audit log with `./export-log.sh`.
- Record a real beta issue with `./record-failure.sh`.
- Record a real beta issue and draft replay regressions with
  `./failure-to-regression.sh`.
- Close a fixed beta issue with `./close-failure.sh` after replay and pytest
  verification.
- Write the daily beta report with `./beta-day-report.sh`.
- Draft replay regressions with `./regression-intake.sh`.
- Write the closeout checklist with `./beta-closeout.sh`.
- Rehearse the local first-run chain with `./first-run-rehearsal.sh`.
- Import local sticker files and rerun local replay checks with
  `./import-stickers.sh`.
- Rehearse the local closeout chain with `./operator-rehearsal.sh`.

Automated scripts start in dry-run. `send-run.sh` refuses to send unless
`ISOTOPE_QQ_ENABLE_SEND=1` is set for that command. `dry-run.sh` and
`send-run.sh` both run `startup-check.sh` before connecting to OneBot.
`diagnostics.sh` does not connect to OneBot; it runs
`isotope-social qq beta-diagnostics --pack-dir . --json`, reads this pack, and
reports the configured group, operator, bot, OneBot URL, reply provider, replay
report, and next steps.
`first-run-rehearsal.sh` runs profile setup, replay, replay scenarios,
startup-check, and diagnostics locally. It does not call `health.sh`,
`dry-run.sh`, `send-run.sh`, or `live-run`.
`import-stickers.sh` reads `sticker-assets/manifest.json`, imports local sticker
files into `../qq-profile/sticker-library.json`, applies that profile, reruns
replay and replay scenarios, then runs startup-check and diagnostics. It stops
with the exact missing file path if a manifest file is absent. It does not call
`health.sh`, `dry-run.sh`, `send-run.sh`, or `live-run`.
`first-run.sh` runs diagnostics, beta-check, startup-check, and health in order.
It stops with replay commands if `logs/replay-report.json` or
`logs/replay-scenarios-report.json` is missing, and it does not call
`dry-run.sh` or `send-run.sh`.
`operator-rehearsal.sh` writes local review and export artifacts tagged with
`operator_rehearsal`, runs the failure-to-regression, close-failure,
regression-intake, beta-day-report, and beta-closeout scripts, then prints
`logs/beta-closeout.json`. Set `ISOTOPE_QQ_REHEARSAL_DATE` to pin the rehearsal
date. It does not connect to OneBot or enable sends.
The generated `config.json` defaults to `runtime.reply_provider = "deterministic"`
for stable replay output. To use LLM-generated text replies, change it to
`runtime.reply_provider = "llm"` and configure the shared Isotope LLM provider;
`startup-check.sh` will block if the LLM provider is missing.
`review-dry-run.sh` only writes a review report; it does not enable sends.
`beta-day-report.sh` combines the dry-run review, exported audit log, and
`logs/failures.json`; it does not enable sends.
`beta-closeout.sh` combines `logs/beta-day-report.json` and
`logs/regression-intake.json`, writes `logs/beta-closeout.json`, and reports
whether the operator can review `send-run.sh`.
`record-failure.sh` appends one structured failure record to
`logs/failures.json`.
`close-failure.sh` marks one matching failure as fixed, writes `resolved_date`,
and preserves the fix note in `logs/failures.json`.
`failure-to-regression.sh` runs `record-failure.sh`, runs
`regression-intake.sh`, then prints the next `qq replay` command(s) to review.
If the failure includes a regression test path, it also prints the next pytest
command(s). It does not connect to OneBot, does not send messages, and does not
run pytest automatically.
`regression-intake.sh` writes replay drafts under `regressions/`; it does not
close failures automatically.
"""


def _required_text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()
