from __future__ import annotations

import json
import os
from pathlib import Path

from isotope.features.social import CharacterCard, StickerLibrary, beta_diagnostics, startup_gate
from isotope.llm.provider import LLMProviderResolution
from tests.unit.features.social.test_social_runner import (
    _prepare_profiled_replay_pack,
    _read_json,
    _write_json,
    main,
)




def test_social_runner_qq_init_profile_writes_editable_role_and_stickers(
    tmp_path: Path,
    capsys,
) -> None:
    profile_dir = tmp_path / "qq-profile"

    code = main(
        [
            "qq",
            "init-profile",
            "--output-dir",
            str(profile_dir),
            "--group",
            "99999",
            "--name",
            "群聊工程猫",
            "--json",
        ]
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["command"] == "init-profile"
    assert payload["output_dir"] == str(profile_dir)
    assert payload["role_card_path"] == str(profile_dir / "role-card.json")
    assert payload["sticker_library_path"] == str(profile_dir / "sticker-library.json")
    assert payload["readme_path"] == str(profile_dir / "README.md")

    role_payload = _read_json(profile_dir / "role-card.json")
    role = CharacterCard.from_dict(role_payload)
    assert role.identity.name == "群聊工程猫"
    assert role.stickers.enabled is True
    assert role.stickers.allow_sticker_only_reply is True
    assert role.group_overrides["99999"]["social_behavior"]["talkativeness"] == 0.4

    stickers = StickerLibrary.from_dict(_read_json(profile_dir / "sticker-library.json"))
    assert [entry.sticker_id for entry in stickers.entries] == [
        "ack-ok",
        "ship-it",
        "need-context",
        "calm-down",
    ]
    assert stickers.entries[0].allowed_groups == ("99999",)
    profile_readme = (profile_dir / "README.md").read_text(encoding="utf-8")
    assert "apply-profile" in profile_readme
    assert 'runtime.reply_provider = "llm"' in profile_readme


def test_social_runner_qq_apply_profile_updates_beta_config_and_beta_check(
    tmp_path: Path,
    capsys,
) -> None:
    beta_dir = tmp_path / "qq-beta"
    profile_dir = tmp_path / "qq-profile"

    assert main(
        [
            "qq",
            "init-beta",
            "--output-dir",
            str(beta_dir),
            "--group",
            "99999",
            "--operator",
            "op",
            "--bot-user-id",
            "bot_qq",
            "--websocket-url",
            "ws://127.0.0.1:3001",
            "--json",
        ]
    ) == 0
    capsys.readouterr()
    assert main(
        [
            "qq",
            "init-profile",
            "--output-dir",
            str(profile_dir),
            "--group",
            "99999",
            "--name",
            "群聊工程猫",
            "--json",
        ]
    ) == 0
    capsys.readouterr()

    code = main(
        [
            "qq",
            "apply-profile",
            "--pack-dir",
            str(beta_dir),
            "--profile-dir",
            str(profile_dir),
            "--json",
        ]
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["command"] == "apply-profile"
    assert payload["config_path"] == str(beta_dir / "config.json")
    assert payload["backup_path"] == str(beta_dir / "config.before-profile.json")
    assert payload["role_card_path"] == str(profile_dir / "role-card.json")
    assert payload["sticker_library_path"] == str(profile_dir / "sticker-library.json")

    config = _read_json(beta_dir / "config.json")
    assert config["role_card_path"] == "../qq-profile/role-card.json"
    assert config["sticker_library_path"] == "../qq-profile/sticker-library.json"
    assert config["runtime"]["reply_provider"] == "deterministic"
    assert "role_card" not in config
    assert "sticker_library" not in config
    assert (beta_dir / "config.before-profile.json").exists()

    assert main(
        ["qq", "inspect", "role", "--config-json", str(beta_dir / "config.json"), "--json"]
    ) == 0
    role_payload = json.loads(capsys.readouterr().out)
    assert role_payload["role"]["identity"]["name"] == "群聊工程猫"
    assert main(
        [
            "qq",
            "inspect",
            "stickers",
            "--config-json",
            str(beta_dir / "config.json"),
            "--json",
        ]
    ) == 0
    sticker_payload = json.loads(capsys.readouterr().out)
    assert sticker_payload["stickers"]["entries"][0]["sticker_id"] == "ack-ok"

    assert main(["qq", "beta-check", "--pack-dir", str(beta_dir), "--json"]) == 0
    check_payload = json.loads(capsys.readouterr().out)
    assert check_payload["ok"] is True


def test_social_runner_qq_import_stickers_writes_valid_profile_library(
    tmp_path: Path,
    capsys,
) -> None:
    beta_dir = tmp_path / "qq-beta"
    profile_dir = tmp_path / "qq-profile"
    source_dir = tmp_path / "sticker-assets"
    source_dir.mkdir()
    (source_dir / "ship.png").write_bytes(b"fake sticker image")
    _write_json(
        source_dir / "manifest.json",
        {
            "stickers": [
                {
                    "sticker_id": "ship-it",
                    "file": "ship.png",
                    "tags": ["ship", "review"],
                    "meaning": "代码通过时使用",
                    "source": "engineering_pack",
                }
            ]
        },
    )

    assert main(
        [
            "qq",
            "init-beta",
            "--output-dir",
            str(beta_dir),
            "--group",
            "99999",
            "--operator",
            "op",
            "--bot-user-id",
            "bot_qq",
            "--websocket-url",
            "ws://127.0.0.1:3001",
            "--json",
        ]
    ) == 0
    capsys.readouterr()
    assert main(
        [
            "qq",
            "init-profile",
            "--output-dir",
            str(profile_dir),
            "--group",
            "99999",
            "--name",
            "群聊工程猫",
            "--json",
        ]
    ) == 0
    capsys.readouterr()

    output = profile_dir / "sticker-library.json"
    code = main(
        [
            "qq",
            "import-stickers",
            "--source-dir",
            str(source_dir),
            "--output",
            str(output),
            "--group",
            "99999",
            "--pack-id",
            "engineering",
            "--json",
        ]
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["command"] == "import-stickers"
    assert payload["output"] == str(output)
    assert payload["entry_count"] == 1
    assert payload["sticker_ids"] == ["ship-it"]

    library_payload = _read_json(output)
    stickers = StickerLibrary.from_dict(library_payload)
    assert stickers.entries[0].sticker_id == "ship-it"
    assert stickers.entries[0].pack_id == "engineering"
    assert stickers.entries[0].media.media_ref == "file://ship.png"
    assert stickers.entries[0].media.local_path == os.path.relpath(
        source_dir / "ship.png",
        start=profile_dir,
    )
    assert stickers.entries[0].allowed_groups == ("99999",)

    assert main(
        [
            "qq",
            "apply-profile",
            "--pack-dir",
            str(beta_dir),
            "--profile-dir",
            str(profile_dir),
            "--json",
        ]
    ) == 0
    capsys.readouterr()
    assert main(["qq", "beta-check", "--pack-dir", str(beta_dir), "--json"]) == 0
    check_payload = json.loads(capsys.readouterr().out)
    assert check_payload["ok"] is True


def test_social_runner_qq_import_stickers_rejects_missing_files(
    tmp_path: Path,
    capsys,
) -> None:
    source_dir = tmp_path / "sticker-assets"
    source_dir.mkdir()
    _write_json(
        source_dir / "manifest.json",
        {
            "stickers": [
                {
                    "sticker_id": "missing",
                    "file": "missing.png",
                    "tags": ["ship"],
                    "meaning": "不存在的素材",
                }
            ]
        },
    )
    output = tmp_path / "sticker-library.json"

    code = main(
        [
            "qq",
            "import-stickers",
            "--source-dir",
            str(source_dir),
            "--output",
            str(output),
            "--group",
            "99999",
            "--pack-id",
            "engineering",
            "--json",
        ]
    )

    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert "sticker file does not exist" in payload["error"]["message"]
    assert not output.exists()


def test_social_runner_qq_startup_check_blocks_missing_sticker_local_path(
    tmp_path: Path,
    capsys,
) -> None:
    beta_dir, report_path = _prepare_profiled_replay_pack(tmp_path, capsys)
    config = _read_json(beta_dir / "config.json")
    sticker_library_path = beta_dir / config["sticker_library_path"]
    stickers = _read_json(sticker_library_path)
    stickers["entries"][0]["media"]["local_path"] = "missing-sticker.png"
    _write_json(sticker_library_path, stickers)

    code = main(
        [
            "qq",
            "startup-check",
            "--pack-dir",
            str(beta_dir),
            "--replay-report",
            str(report_path),
            "--json",
        ]
    )

    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    failed = [check for check in payload["checks"] if not check["ok"]]
    assert [check["name"] for check in failed] == ["sticker_assets"]
    assert "sticker local_path does not exist" in failed[0]["errors"][0]
    assert failed[0]["missing_local_paths"] == ["missing-sticker.png"]


def test_social_runner_qq_startup_check_blocks_replay_required_sticker_missing_from_library(
    tmp_path: Path,
    capsys,
) -> None:
    beta_dir, report_path = _prepare_profiled_replay_pack(tmp_path, capsys)
    config = _read_json(beta_dir / "config.json")
    sticker_library_path = beta_dir / config["sticker_library_path"]
    stickers = _read_json(sticker_library_path)
    stickers["entries"] = [
        entry for entry in stickers["entries"] if entry["sticker_id"] != "ship-it"
    ]
    _write_json(sticker_library_path, stickers)

    code = main(
        [
            "qq",
            "startup-check",
            "--pack-dir",
            str(beta_dir),
            "--replay-report",
            str(report_path),
            "--json",
        ]
    )

    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    failed = [check for check in payload["checks"] if not check["ok"]]
    assert [check["name"] for check in failed] == ["sticker_assets"]
    assert failed[0]["required_sticker_ids"] == ["ship-it"]
    assert failed[0]["missing_required_sticker_ids"] == ["ship-it"]
    assert "replay required sticker ids missing from sticker-library" in (
        failed[0]["errors"][0]
    )


def test_social_runner_qq_startup_check_passes_after_profile_and_replay(
    tmp_path: Path,
    capsys,
) -> None:
    beta_dir, report_path = _prepare_profiled_replay_pack(tmp_path, capsys)

    code = main(
        [
            "qq",
            "startup-check",
            "--pack-dir",
            str(beta_dir),
            "--replay-report",
            str(report_path),
            "--json",
        ]
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["command"] == "startup-check"
    assert payload["ready"] is True
    assert [check["name"] for check in payload["checks"]] == [
        "beta_pack",
        "profile_assets",
        "sticker_assets",
        "llm_reply_provider",
        "replay_report",
    ]
    assert all(check["ok"] for check in payload["checks"])


def test_social_runner_qq_beta_diagnostics_reports_ready_pack(
    tmp_path: Path,
    capsys,
) -> None:
    beta_dir, _report_path = _prepare_profiled_replay_pack(tmp_path, capsys)

    code = main(["qq", "beta-diagnostics", "--pack-dir", str(beta_dir), "--json"])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ready"
    assert payload["command"] == "beta-diagnostics"
    assert payload["pack_dir"] == str(beta_dir)
    assert payload["summary"]["allowed_groups"] == ["99999"]
    assert payload["summary"]["operator_user_ids"] == ["op"]
    assert payload["summary"]["bot_user_id"] == "bot_qq"
    assert payload["summary"]["websocket_url"] == "ws://127.0.0.1:3001"
    assert payload["summary"]["reply_provider"] == "deterministic"
    assert payload["summary"]["llm"] == {
        "required": False,
        "configured": None,
        "provider_name": None,
        "reason_code": "deterministic_reply_provider",
    }
    assert payload["summary"]["profile"]["applied"] is True
    assert payload["summary"]["profile"]["role_name"] == "群聊工程猫"
    assert payload["summary"]["stickers"]["entry_count"] > 0
    assert payload["summary"]["replay_report"]["exists"] is True
    assert payload["next_steps"][0]["command"] == "./health.sh"


def test_social_runner_qq_beta_diagnostics_guides_missing_profile(
    tmp_path: Path,
    capsys,
) -> None:
    beta_dir = tmp_path / "qq-beta"
    assert main(
        [
            "qq",
            "init-beta",
            "--output-dir",
            str(beta_dir),
            "--group",
            "99999",
            "--operator",
            "op",
            "--bot-user-id",
            "bot_qq",
            "--websocket-url",
            "ws://127.0.0.1:3001",
            "--json",
        ]
    ) == 0
    capsys.readouterr()

    code = main(["qq", "beta-diagnostics", "--pack-dir", str(beta_dir), "--json"])

    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "needs_action"
    assert payload["command"] == "beta-diagnostics"
    assert payload["summary"]["profile"]["applied"] is False
    commands = [step["command"] for step in payload["next_steps"]]
    assert "isotope-social qq init-profile" in commands[0]
    assert "isotope-social qq apply-profile" in commands[1]
    assert commands[-1] == "isotope-social qq beta-diagnostics --pack-dir . --json"


def test_social_runner_qq_beta_diagnostics_reports_missing_llm_provider(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    beta_dir, _report_path = _prepare_profiled_replay_pack(tmp_path, capsys)
    config_path = beta_dir / "config.json"
    config = _read_json(config_path)
    config["runtime"]["reply_provider"] = "llm"
    _write_json(config_path, config)
    monkeypatch.setattr(
        beta_diagnostics,
        "resolve_llm_chat_provider",
        lambda: LLMProviderResolution(
            status="missing_configuration",
            reason_code="llm_provider_not_configured",
            provider_name="auto",
        ),
    )
    monkeypatch.setattr(
        startup_gate,
        "resolve_llm_chat_provider",
        lambda: LLMProviderResolution(
            status="missing_configuration",
            reason_code="llm_provider_not_configured",
            provider_name="auto",
        ),
    )

    code = main(["qq", "beta-diagnostics", "--pack-dir", str(beta_dir), "--json"])

    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "needs_action"
    assert payload["summary"]["reply_provider"] == "llm"
    assert payload["summary"]["llm"] == {
        "required": True,
        "configured": False,
        "provider_name": "auto",
        "reason_code": "llm_provider_not_configured",
    }
    assert payload["next_steps"][0]["name"] == "fix_llm_reply_provider"


def test_social_runner_qq_startup_check_blocks_llm_reply_without_provider(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    beta_dir, report_path = _prepare_profiled_replay_pack(tmp_path, capsys)
    config_path = beta_dir / "config.json"
    config = _read_json(config_path)
    config["runtime"]["reply_provider"] = "llm"
    _write_json(config_path, config)
    monkeypatch.setattr(
        startup_gate,
        "resolve_llm_chat_provider",
        lambda: LLMProviderResolution(
            status="missing_configuration",
            reason_code="llm_provider_not_configured",
            provider_name="auto",
        ),
    )

    code = main(
        [
            "qq",
            "startup-check",
            "--pack-dir",
            str(beta_dir),
            "--replay-report",
            str(report_path),
            "--json",
        ]
    )

    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "blocked"
    failed = [check for check in payload["checks"] if not check["ok"]]
    assert [check["name"] for check in failed] == ["llm_reply_provider"]
    assert failed[0]["reason_code"] == "llm_provider_not_configured"


def test_social_runner_qq_startup_check_blocks_missing_profile_and_replay(
    tmp_path: Path,
    capsys,
) -> None:
    beta_dir = tmp_path / "qq-beta"
    assert main(
        [
            "qq",
            "init-beta",
            "--output-dir",
            str(beta_dir),
            "--group",
            "99999",
            "--operator",
            "op",
            "--bot-user-id",
            "bot_qq",
            "--websocket-url",
            "ws://127.0.0.1:3001",
            "--json",
        ]
    ) == 0
    capsys.readouterr()

    code = main(
        [
            "qq",
            "startup-check",
            "--pack-dir",
            str(beta_dir),
            "--replay-report",
            str(beta_dir / "logs" / "replay-report.json"),
            "--json",
        ]
    )

    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "blocked"
    assert payload["command"] == "startup-check"
    assert payload["ready"] is False
    failed = [check["name"] for check in payload["checks"] if not check["ok"]]
    assert failed == ["profile_assets", "sticker_assets", "replay_report"]
