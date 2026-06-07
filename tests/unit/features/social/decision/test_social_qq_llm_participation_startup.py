from __future__ import annotations

import json

from isotope.features.social import beta_diagnostics, startup_gate
from isotope.features.social.runner import main
from isotope.llm.provider import LLMProviderResolution
from tests.unit.features.social.test_social_runner import (
    _prepare_profiled_replay_pack,
    _read_json,
    _write_json,
)


def _missing_provider() -> LLMProviderResolution:
    return LLMProviderResolution(
        status="missing_configuration",
        reason_code="llm_provider_not_configured",
        provider_name="auto",
    )


def test_startup_check_blocks_llm_participation_without_provider(
    tmp_path,
    capsys,
    monkeypatch,
) -> None:
    beta_dir, report_path = _prepare_profiled_replay_pack(tmp_path, capsys)
    config_path = beta_dir / "config.json"
    config = _read_json(config_path)
    config["runtime"]["participation_provider"] = "llm"
    _write_json(config_path, config)
    monkeypatch.setattr(startup_gate, "resolve_llm_chat_provider", _missing_provider)

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
    assert [check["name"] for check in failed] == ["llm_reply_provider"]
    assert failed[0]["reply_provider"] == "deterministic"
    assert failed[0]["participation_provider"] == "llm"
    assert failed[0]["reason_code"] == "llm_provider_not_configured"


def test_beta_diagnostics_reports_missing_llm_participation_provider(
    tmp_path,
    capsys,
    monkeypatch,
) -> None:
    beta_dir, _report_path = _prepare_profiled_replay_pack(tmp_path, capsys)
    config_path = beta_dir / "config.json"
    config = _read_json(config_path)
    config["runtime"]["participation_provider"] = "llm"
    _write_json(config_path, config)
    monkeypatch.setattr(
        beta_diagnostics,
        "resolve_llm_chat_provider",
        _missing_provider,
    )
    monkeypatch.setattr(startup_gate, "resolve_llm_chat_provider", _missing_provider)

    code = main(["qq", "beta-diagnostics", "--pack-dir", str(beta_dir), "--json"])

    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "needs_action"
    assert payload["summary"]["reply_provider"] == "deterministic"
    assert payload["summary"]["participation_provider"] == "llm"
    assert payload["summary"]["llm"] == {
        "required": True,
        "configured": False,
        "provider_name": "auto",
        "reason_code": "llm_provider_not_configured",
    }
    assert payload["next_steps"][0]["name"] == "fix_llm_reply_provider"
