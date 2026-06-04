"""Verify a generated QQ beta pack before operator use."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .beta_pack import SCRIPT_NAMES
from .character_card import CharacterCard
from .stickers import StickerLibrary


@dataclass(frozen=True)
class QQBetaCheckConfig:
    pack_dir: Path

    def __post_init__(self) -> None:
        if not str(self.pack_dir).strip():
            raise ValueError("pack-dir must be a non-empty path")


@dataclass(frozen=True)
class QQBetaCheckResult:
    pack_dir: Path
    checks: tuple[dict[str, Any], ...]
    export_log_path: Path

    @property
    def ok(self) -> bool:
        return all(bool(check.get("ok")) for check in self.checks)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "pack_dir": str(self.pack_dir),
            "ok": self.ok,
            "checks": list(self.checks),
            "export_log_path": str(self.export_log_path),
        }


def check_qq_beta_pack(config: QQBetaCheckConfig) -> QQBetaCheckResult:
    pack_dir = config.pack_dir
    if not pack_dir.exists() or not pack_dir.is_dir():
        raise ValueError(f"beta pack directory does not exist: {pack_dir}")

    required_check = _check_required_files(pack_dir)
    config_payload = _load_pack_config(pack_dir / "config.json")
    group_id = _first_allowed_group(config_payload)
    export_log_path = pack_dir / "logs" / f"qq-{group_id}.json"

    checks = [
        required_check,
        _check_config_payload(config_payload, base_dir=pack_dir),
        _check_shell_syntax(pack_dir),
        _check_operator_scripts(pack_dir),
        _check_send_guard(pack_dir),
    ]
    failed = [check for check in checks if not check["ok"]]
    if failed:
        names = ", ".join(str(check["name"]) for check in failed)
        raise ValueError(f"beta pack checks failed: {names}")
    return QQBetaCheckResult(
        pack_dir=pack_dir,
        checks=tuple(checks),
        export_log_path=export_log_path,
    )


def _check_required_files(pack_dir: Path) -> dict[str, Any]:
    required = ["config.json", "state", "logs", *SCRIPT_NAMES]
    missing = [name for name in required if not (pack_dir / name).exists()]
    return {
        "name": "required_files",
        "ok": not missing,
        "required": required,
        "missing": missing,
    }


def _load_pack_config(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("config.json must contain a JSON object")
    return payload


def _check_config_payload(payload: dict[str, Any], *, base_dir: Path) -> dict[str, Any]:
    group_policy = _dict_value(payload, "group_policy")
    allowed_groups = group_policy.get("allowed_groups")
    operator_user_ids = group_policy.get("operator_user_ids")
    errors: list[str] = []
    if not isinstance(payload.get("bot_user_id"), str) or not payload["bot_user_id"].strip():
        errors.append("bot_user_id")
    if not isinstance(allowed_groups, list) or not allowed_groups:
        errors.append("group_policy.allowed_groups")
    if not isinstance(operator_user_ids, list) or not operator_user_ids:
        errors.append("group_policy.operator_user_ids")
    try:
        role_card = _asset_payload(
            payload,
            inline_key="role_card",
            path_key="role_card_path",
            base_dir=base_dir,
        )
        CharacterCard.from_dict(role_card)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"role_card:{exc}")
    try:
        sticker_library = _asset_payload(
            payload,
            inline_key="sticker_library",
            path_key="sticker_library_path",
            base_dir=base_dir,
        )
        StickerLibrary.from_dict(sticker_library)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"sticker_library:{exc}")
    return {"name": "config_json", "ok": not errors, "errors": errors}


def _check_shell_syntax(pack_dir: Path) -> dict[str, Any]:
    results = [_run(["bash", "-n", script], cwd=pack_dir) for script in SCRIPT_NAMES]
    failures = [
        {"script": SCRIPT_NAMES[index], "stderr": result.stderr.strip()}
        for index, result in enumerate(results)
        if result.returncode != 0
    ]
    return {"name": "shell_syntax", "ok": not failures, "failures": failures}


def _check_operator_scripts(pack_dir: Path) -> dict[str, Any]:
    scripts = ("pause.sh", "resume.sh", "export-log.sh")
    results = [_run([f"./{script}"], cwd=pack_dir) for script in scripts]
    failures = [
        {
            "script": scripts[index],
            "returncode": result.returncode,
            "stderr": result.stderr.strip(),
        }
        for index, result in enumerate(results)
        if result.returncode != 0
    ]
    return {"name": "operator_scripts", "ok": not failures, "failures": failures}


def _check_send_guard(pack_dir: Path) -> dict[str, Any]:
    env = _script_env()
    env.pop("ISOTOPE_QQ_ENABLE_SEND", None)
    result = _run(["./send-run.sh"], cwd=pack_dir, env=env)
    refused = result.returncode == 2 and "Refusing to send" in result.stderr
    return {
        "name": "send_guard",
        "ok": refused,
        "returncode": result.returncode,
        "stderr": result.stderr.strip(),
    }


def _run(
    args: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        env=env or _script_env(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _script_env() -> dict[str, str]:
    env = dict(os.environ)
    python_bin_dir = str(Path(sys.executable).parent)
    src_dir = str(Path(__file__).resolve().parents[3])
    env["PATH"] = python_bin_dir + os.pathsep + env.get("PATH", "")
    env["PYTHONPATH"] = src_dir + os.pathsep + env.get("PYTHONPATH", "")
    return env


def _first_allowed_group(payload: dict[str, Any]) -> str:
    group_policy = _dict_value(payload, "group_policy")
    allowed_groups = group_policy.get("allowed_groups")
    if not isinstance(allowed_groups, list) or not allowed_groups:
        raise ValueError("group_policy.allowed_groups must contain at least one group")
    return str(allowed_groups[0])


def _dict_value(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be a JSON object")
    return value


def _asset_payload(
    payload: dict[str, Any],
    *,
    inline_key: str,
    path_key: str,
    base_dir: Path,
) -> dict[str, Any]:
    if inline_key in payload:
        return _dict_value(payload, inline_key)
    path_value = payload.get(path_key)
    if not isinstance(path_value, str) or not path_value.strip():
        raise ValueError(f"{inline_key} or {path_key} is required")
    path = Path(path_value)
    if not path.is_absolute():
        path = base_dir / path
    return _load_pack_config(path)
