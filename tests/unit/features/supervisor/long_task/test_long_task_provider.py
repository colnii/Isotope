from __future__ import annotations

from typing import Any

import pytest

from isotope.features.supervisor.long_task.provider import (
    resolve_long_task_planner_provider_from_env,
)


def test_resolve_long_task_provider_can_pin_mimo_pool_entry(tmp_path):
    pool = tmp_path / "pool.toml"
    pool.write_text(
        """
[[keys]]
provider = "backup"
base_url = "https://backup.example/v1"
model = "backup-model"
api_keys = ["env:BACKUP_KEY"]

[[keys]]
provider = "mimo"
base_url = "https://mimo.example/v1"
model = "mimo-v2.5-pro"
api_keys = ["env:MIMO_KEY"]
""".strip(),
        encoding="utf-8",
    )
    calls: list[dict[str, Any]] = []

    def transport(url, payload, headers, timeout):
        calls.append(
            {
                "url": url,
                "model": payload["model"],
                "authorization": headers["Authorization"],
                "timeout": timeout,
            }
        )
        return {
            "model": payload["model"],
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"content": "{}"},
                }
            ],
            "usage": {"total_tokens": 1},
        }

    provider = resolve_long_task_planner_provider_from_env(
        {
            "SUPERVISOR_LLM_POOL_TOML_FILES": str(pool),
            "ISOTOPE_LONG_TASK_LLM_PROVIDER": "mimo",
            "BACKUP_KEY": "backup-secret",
            "MIMO_KEY": "mimo-secret",
        },
        timeout=7,
        transport=transport,
    )

    response = provider.generate([{"role": "user", "content": "ping"}])

    assert response.provider == "mimo"
    assert response.model == "mimo-v2.5-pro"
    assert calls == [
        {
            "url": "https://mimo.example/v1/chat/completions",
            "model": "mimo-v2.5-pro",
            "authorization": "Bearer mimo-secret",
            "timeout": 7,
        }
    ]


def test_resolve_long_task_provider_reports_missing_pinned_entry(tmp_path):
    pool = tmp_path / "pool.toml"
    pool.write_text(
        """
[[keys]]
provider = "backup"
base_url = "https://backup.example/v1"
model = "backup-model"
api_keys = ["env:BACKUP_KEY"]
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="provider mimo"):
        resolve_long_task_planner_provider_from_env(
            {
                "SUPERVISOR_LLM_POOL_TOML_FILES": str(pool),
                "ISOTOPE_LONG_TASK_LLM_PROVIDER": "mimo",
                "BACKUP_KEY": "backup-secret",
            }
        )
