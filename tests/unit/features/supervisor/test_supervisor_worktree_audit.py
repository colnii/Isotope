from __future__ import annotations

import argparse
import json

from isotope.features.supervisor.commands.parser import build_parser
from isotope.features.supervisor.commands.handlers.worktree_audit import (
    audit_worktree_records,
    handle_worktree_audit_command,
    launch_coordination_preflight_from_records,
    parse_worktree_list_porcelain,
    parse_worktree_status_porcelain,
)


def test_parse_worktree_list_porcelain_keeps_branch_and_detached_records():
    records = parse_worktree_list_porcelain(
        "\n".join(
            [
                "worktree /repo",
                "HEAD abc123",
                "branch refs/heads/main",
                "",
                "worktree /repo/.worktrees/research-tavily-execution",
                "HEAD def456",
                "branch refs/heads/feature/research-tavily-execution",
                "",
                "worktree /repo/.worktrees/memory-summary-surface",
                "HEAD 999999",
                "detached",
                "",
            ]
        )
    )

    assert records == [
        {
            "path": "/repo",
            "head": "abc123",
            "branch": "main",
            "detached": False,
        },
        {
            "path": "/repo/.worktrees/research-tavily-execution",
            "head": "def456",
            "branch": "feature/research-tavily-execution",
            "detached": False,
        },
        {
            "path": "/repo/.worktrees/memory-summary-surface",
            "head": "999999",
            "branch": None,
            "detached": True,
        },
    ]


def test_audit_worktree_records_warns_on_shared_distinctive_topic_only():
    payload = audit_worktree_records(
        [
            {
                "path": "/repo/.worktrees/research-tavily-execution",
                "branch": "feature/research-tavily-execution",
                "head": "111",
                "detached": False,
            },
            {
                "path": "/repo/.worktrees/tavily-api-provider",
                "branch": "feature/tavily-api-provider",
                "head": "222",
                "detached": False,
            },
            {
                "path": "/repo/.worktrees/agent-loop-summary-surfaces",
                "branch": "feature/agent-loop-summary-surfaces",
                "head": "333",
                "detached": False,
            },
            {
                "path": "/repo/.worktrees/memory-summary-surface",
                "branch": "feature/memory-summary-surface",
                "head": "444",
                "detached": False,
            },
        ]
    )

    assert payload["status"] == "attention"
    assert payload["summary"]["worktrees"] == 4
    assert payload["summary"]["dirty_worktrees"] == 0
    assert payload["summary"]["duplicate_candidates"] == 1
    assert payload["summary"]["overlapping_modified_files"] == 0
    candidate = payload["duplicate_candidates"][0]
    assert candidate["kind"] == "shared_topic"
    assert candidate["shared_tokens"] == ["tavily"]
    assert [item["branch"] for item in candidate["worktrees"]] == [
        "feature/research-tavily-execution",
        "feature/tavily-api-provider",
    ]


def test_parse_worktree_status_porcelain_keeps_changed_paths():
    status = parse_worktree_status_porcelain(
        "\n".join(
            [
                " M src/isotope/features/supervisor/commands/dispatch.py",
                "A  tests/unit/features/supervisor/test_worktree_audit.py",
                "R  old_name.py -> new_name.py",
                "?? docs/current/coordination.md",
            ]
        )
    )

    assert status == [
        "docs/current/coordination.md",
        "new_name.py",
        "src/isotope/features/supervisor/commands/dispatch.py",
        "tests/unit/features/supervisor/test_worktree_audit.py",
    ]


def test_audit_worktree_records_warns_on_overlapping_dirty_files():
    payload = audit_worktree_records(
        [
            {
                "path": "/repo/.worktrees/worker-a",
                "branch": "feature/agent-loop-summary",
                "head": "111",
                "detached": False,
                "dirty": True,
                "modified_files": [
                    "docs/current/status.md",
                    "src/isotope/features/supervisor/runner.py",
                ],
            },
            {
                "path": "/repo/.worktrees/worker-b",
                "branch": "feature/memory-summary",
                "head": "222",
                "detached": False,
                "dirty": True,
                "modified_files": [
                    "docs/current/status.md",
                    "tests/unit/features/supervisor/test_status.py",
                ],
            },
        ]
    )

    assert payload["status"] == "attention"
    assert payload["summary"]["dirty_worktrees"] == 2
    assert payload["summary"]["overlapping_modified_files"] == 1
    overlap = payload["overlapping_modified_files"][0]
    assert overlap["kind"] == "overlapping_modified_files"
    assert overlap["files"] == ["docs/current/status.md"]
    assert [item["branch"] for item in overlap["worktrees"]] == [
        "feature/agent-loop-summary",
        "feature/memory-summary",
    ]


def test_launch_coordination_preflight_warns_about_existing_topic_worktree():
    payload = launch_coordination_preflight_from_records(
        [
            {
                "path": "/repo",
                "branch": "main",
                "head": "000",
                "detached": False,
            },
            {
                "path": "/repo/.worktrees/research-quality-gate",
                "branch": "feature/research-quality-gate",
                "head": "111",
                "detached": False,
                "dirty": True,
                "modified_files": ["src/isotope/features/research/quality.py"],
            },
            {
                "path": "/repo/.worktrees/screen-allowlist-list",
                "branch": "feature/screen-allowlist-list",
                "head": "222",
                "detached": False,
            },
        ],
        target_name="research-quality-gate",
        goal="完善 research quality gate 的 promotion guard。",
    )

    assert payload["kind"] == "launch_coordination_preflight"
    assert payload["status"] == "needs_user"
    assert payload["summary"] == {"candidates": 1}
    assert payload["query"]["target_name"] == "research-quality-gate"
    assert payload["query"]["topic_tokens"] == [
        "gate",
        "guard",
        "promotion",
        "quality",
        "research",
    ]
    assert payload["candidates"][0]["branch"] == "feature/research-quality-gate"
    assert payload["candidates"][0]["dirty"] is True
    assert payload["candidates"][0]["modified_files"] == [
        "src/isotope/features/research/quality.py"
    ]
    assert payload["candidates"][0]["shared_tokens"] == [
        "gate",
        "quality",
        "research",
    ]


def test_launch_coordination_preflight_ignores_unrelated_worktrees():
    payload = launch_coordination_preflight_from_records(
        [
            {
                "path": "/repo/.worktrees/screen-allowlist-list",
                "branch": "feature/screen-allowlist-list",
                "head": "222",
                "detached": False,
            },
        ],
        target_name="research-quality-gate",
        goal="完善 research quality gate 的 promotion guard。",
    )

    assert payload["status"] == "ok"
    assert payload["summary"] == {"candidates": 0}
    assert payload["candidates"] == []


def test_worktree_audit_command_prints_json_payload(capsys):
    class Api:
        class subprocess:
            @staticmethod
            def run(command, check, text, capture_output):
                assert command[:3] == ["git", "-C", "/repo"]
                assert check is False
                assert text is True
                assert capture_output is True

                class Completed:
                    returncode = 0
                    stdout = ""
                    stderr = ""

                if command[3:] == ["worktree", "list", "--porcelain"]:
                    Completed.stdout = (
                        "worktree /repo\n"
                        "HEAD abc123\n"
                        "branch refs/heads/main\n"
                    )
                    return Completed()
                if command[3:] == ["status", "--porcelain=v1"]:
                    Completed.stdout = " M README.md\n"
                    return Completed()
                raise AssertionError(command)

        @staticmethod
        def _print_json(payload):
            print(json.dumps(payload, sort_keys=True))

    args = argparse.Namespace(repo_root="/repo", json=True)

    assert handle_worktree_audit_command(args, api=Api) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "supervisor_worktree_audit"
    assert payload["summary"]["worktrees"] == 1
    assert payload["summary"]["dirty_worktrees"] == 1


def test_worktree_audit_parser_accepts_repo_root_and_json():
    args = build_parser().parse_args(
        ["worktree-audit", "--repo-root", "/repo", "--json"]
    )

    assert args.command == "worktree-audit"
    assert args.repo_root == "/repo"
    assert args.json is True
