from __future__ import annotations

import argparse
from pathlib import Path

from isotope.features.supervisor.commands.llm.execution import execute_launch_action


def test_execute_launch_action_skips_when_coordination_preflight_needs_user(
    tmp_path,
):
    class Api:
        class subprocess:
            class SubprocessError(Exception):
                pass

        MERGE_DISPATCH_WORKER_ROLE = "merge_dispatch"
        DEFAULT_WORKER_PROFILE = "coding"
        WORKER_PROFILE_DEFAULTS = {"coding": {"model": "gpt-5.5", "config": ()}}
        WORKER_PROFILE_CHOICES = ("coding",)

        @staticmethod
        def lane_failure_state(*, codex_home: Path, name: str):
            return None

        @staticmethod
        def _run_budget_state(*, codex_home: Path, name: str, max_run_minutes: int):
            return None

        @staticmethod
        def default_registry_path(codex_home: Path) -> Path:
            return codex_home / "supervisor" / "managed.jsonl"

        @staticmethod
        def read_managed_records(path: Path):
            return []

        @staticmethod
        def _pid_is_running(pid: int) -> bool:
            return False

        @staticmethod
        def prompt_cooldown_state(
            *,
            codex_home: Path,
            name: str,
            cooldown_seconds: int,
        ):
            return None

        @staticmethod
        def _launch_coordination_preflight(
            *,
            cwd: Path,
            target_name: str,
            goal: str,
        ):
            assert cwd == tmp_path
            assert target_name == "research-quality-gate"
            assert "research quality gate" in goal
            return {
                "kind": "launch_coordination_preflight",
                "status": "needs_user",
                "summary": {"candidates": 1},
                "candidates": [
                    {
                        "path": str(tmp_path / ".worktrees/research-quality-gate"),
                        "branch": "feature/research-quality-gate",
                        "shared_tokens": ["gate", "quality", "research"],
                    }
                ],
            }

        @staticmethod
        def _prepare_launch_worktree(*, cwd: Path, target_name: str):
            raise AssertionError("launch should stop before creating a worktree")

    args = argparse.Namespace(
        codex_home=str(tmp_path / ".codex"),
        max_run_minutes=0,
        prompt_cooldown=0,
    )

    result = execute_launch_action(
        args,
        {
            "kind": "launch_session",
            "target_name": "research-quality-gate",
            "cwd": str(tmp_path),
            "prompt": "完善 research quality gate 的 promotion guard。",
        },
        api=Api,
    )

    assert result == {
        "kind": "launch_session",
        "skipped": True,
        "reason": "coordination preflight needs user",
        "target_name": "research-quality-gate",
        "coordination_preflight": {
            "kind": "launch_coordination_preflight",
            "status": "needs_user",
            "summary": {"candidates": 1},
            "candidates": [
                {
                    "path": str(tmp_path / ".worktrees/research-quality-gate"),
                    "branch": "feature/research-quality-gate",
                    "shared_tokens": ["gate", "quality", "research"],
                }
            ],
        },
    }
