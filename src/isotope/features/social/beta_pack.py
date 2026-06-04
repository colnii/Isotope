"""Generate operator files for a controlled QQ beta."""

from __future__ import annotations

import json
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCRIPT_NAMES = (
    "beta-day-report.sh",
    "diagnostics.sh",
    "first-run.sh",
    "health.sh",
    "startup-check.sh",
    "dry-run.sh",
    "review-dry-run.sh",
    "send-run.sh",
    "pause.sh",
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
    if name == "diagnostics.sh":
        command = _diagnostics_command()
        return f"{common}\n{command}\n"
    if name == "first-run.sh":
        command = _first_run_command(config)
        return f"{common}\n{command}\n"
    if name == "health.sh":
        command = _live_run_command(config, max_events=0, send=False)
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
    replay_command = _qq_replay_command(config)
    return (
        "./diagnostics.sh || true\n"
        "isotope-social qq beta-check --pack-dir . --json\n"
        "if ! [ -f logs/replay-report.json ]; then\n"
        '  echo "Missing logs/replay-report.json. Run these commands before first-run:" >&2\n'
        "  echo "
        f"{shlex.quote(_init_replay_command(config))} >&2\n"
        "  echo "
        f"{shlex.quote(replay_command)} >&2\n"
        "  exit 2\n"
        "fi\n"
        "./startup-check.sh\n"
        "./health.sh\n"
    )


def _init_replay_command(config: QQBetaPackConfig) -> str:
    parts = [
        "isotope-social",
        "qq",
        "init-replay",
        "--output",
        "replay.json",
        "--group",
        config.group_id,
        "--bot-user-id",
        config.bot_user_id,
        "--json",
    ]
    return " ".join(shlex.quote(part) for part in parts)


def _qq_replay_command(config: QQBetaPackConfig) -> str:
    parts = [
        "isotope-social",
        "qq",
        "replay",
        "--config-json",
        "config.json",
        "--state-root",
        "state",
        "--replay-json",
        "replay.json",
        "--output",
        "logs/replay-report.json",
        "--json",
    ]
    return " ".join(shlex.quote(part) for part in parts)


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

1. Apply an editable profile pack.
2. Create and run replay.
3. Run `./first-run.sh`.
4. Run `./diagnostics.sh` again after config or profile edits.
5. Run `./dry-run.sh`.
6. Run `./review-dry-run.sh` and inspect `logs/dry-run-review.json`.
7. Run `./export-log.sh`.
8. Record observed issues in `logs/failures.json`.
9. Run `./beta-day-report.sh` and inspect `logs/beta-day-report.json`.
10. Run `./regression-intake.sh` for open failures and inspect `regressions/`.
11. Only after dry-run behavior is acceptable, run:

```bash
ISOTOPE_QQ_ENABLE_SEND=1 ./send-run.sh
```

## Stop and inspect

- Pause the group with `./pause.sh`.
- Resume with `./resume.sh` only after the issue is understood.
- Export the audit log with `./export-log.sh`.
- Write the daily beta report with `./beta-day-report.sh`.
- Draft replay regressions with `./regression-intake.sh`.

Automated scripts start in dry-run. `send-run.sh` refuses to send unless
`ISOTOPE_QQ_ENABLE_SEND=1` is set for that command. `dry-run.sh` and
`send-run.sh` both run `startup-check.sh` before connecting to OneBot.
`diagnostics.sh` does not connect to OneBot; it runs
`isotope-social qq beta-diagnostics --pack-dir . --json`, reads this pack, and
reports the configured group, operator, bot, OneBot URL, reply provider, replay
report, and next steps.
`first-run.sh` runs diagnostics, beta-check, startup-check, and health in order.
It stops with replay commands if `logs/replay-report.json` is missing, and it
does not call `dry-run.sh` or `send-run.sh`.
The generated `config.json` defaults to `runtime.reply_provider = "deterministic"`
for stable replay output. To use LLM-generated text replies, change it to
`runtime.reply_provider = "llm"` and configure the shared Isotope LLM provider;
`startup-check.sh` will block if the LLM provider is missing.
`review-dry-run.sh` only writes a review report; it does not enable sends.
`beta-day-report.sh` combines the dry-run review, exported audit log, and
`logs/failures.json`; it does not enable sends.
`regression-intake.sh` writes replay drafts under `regressions/`; it does not
close failures automatically.
"""


def _required_text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()
