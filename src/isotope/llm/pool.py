"""本机 TOML 模型号池解析。"""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

DEFAULT_LLM_MAX_TOKENS = 512


@dataclass(frozen=True)
class PoolEntry:
    """号池里的一条可尝试模型配置。"""

    provider: str
    api_key: str
    base_url: str
    model: str
    max_tokens: int | None = None


def resolve_pool_entries_from_env(
    environ: Mapping[str, str] | None = None,
    *,
    agent_name: str | None = None,
    env_var: str = "ISOTOPE_LLM_POOL_TOML_FILES",
    default_paths: Sequence[Path] = (),
    default_provider: str = "llm_pool",
) -> tuple[PoolEntry, ...]:
    """从环境变量和默认路径读取 TOML 号池，不绑定具体调用场景。"""
    env = os.environ if environ is None else environ
    return tuple(
        _load_pool_entries(
            _pool_toml_paths(env, env_var=env_var, default_paths=default_paths),
            env,
            agent_name=agent_name,
            default_provider=default_provider,
        )
    )


def _pool_toml_paths(
    env: Mapping[str, str],
    *,
    env_var: str,
    default_paths: Sequence[Path],
) -> list[Path]:
    raw = _env_string(env, env_var)
    if raw:
        return [Path(path.strip()) for path in raw.split(",") if path.strip()]
    return list(default_paths)


def _load_pool_entries(
    files: list[Path],
    env: Mapping[str, str],
    *,
    agent_name: str | None = None,
    default_provider: str = "llm_pool",
) -> list[PoolEntry]:
    entries: list[PoolEntry] = []
    for path in files:
        if not path.is_file():
            continue
        data = tomllib.loads(path.read_text(encoding="utf-8"))

        if isinstance(data.get("agents"), list):
            for agent in data["agents"]:
                if not isinstance(agent, dict):
                    continue
                name = _optional_toml_str(agent, "name")
                if name is None:
                    continue
                if agent_name is not None and name != agent_name:
                    continue
                provider_list = agent.get("providers")
                if not isinstance(provider_list, list):
                    continue
                for item in provider_list:
                    if isinstance(item, dict):
                        _append_entries_from_toml_item(
                            entries,
                            item,
                            env,
                            default_provider=default_provider,
                        )

        if isinstance(data.get("keys"), list):
            for item in data["keys"]:
                if isinstance(item, dict):
                    _append_entries_from_toml_item(
                        entries,
                        item,
                        env,
                        default_provider=default_provider,
                    )

    return entries


def _append_entries_from_toml_item(
    entries: list[PoolEntry],
    item: dict[str, object],
    env: Mapping[str, str],
    *,
    default_provider: str,
) -> None:
    provider = _optional_toml_str(item, "provider") or default_provider
    base_url = _require_toml_str(item, "base_url")
    model = _require_toml_str(item, "model")
    max_tokens_val = item.get("max_tokens")
    if max_tokens_val is not None:
        if not isinstance(max_tokens_val, int) or max_tokens_val <= 0:
            raise ValueError(
                "TOML pool entry max_tokens must be a positive integer, "
                f"got: {max_tokens_val!r}"
            )
    raw_keys = item.get("api_keys")
    if not isinstance(raw_keys, list):
        return
    for entry in raw_keys:
        if not isinstance(entry, str) or not entry.strip():
            continue
        entry = entry.strip()
        if entry.startswith("env:"):
            api_key = env.get(entry[4:])
            if not api_key:
                continue
        else:
            api_key = entry
        entries.append(
            PoolEntry(
                provider=provider,
                api_key=api_key,
                base_url=base_url.rstrip("/"),
                model=model,
                max_tokens=max_tokens_val,
            )
        )


def _require_toml_str(item: dict[str, object], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"TOML pool entry missing required string field: {key}")
    return value.strip()


def _optional_toml_str(item: dict[str, object], key: str) -> str | None:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _env_string(env: Mapping[str, str], name: str) -> str | None:
    value = env.get(name)
    if not value:
        return None
    return value.strip() or None
