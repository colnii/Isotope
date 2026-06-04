"""Worktree coordination audit for the Supervisor CLI."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any


GENERIC_TOPIC_TOKENS = {
    "api",
    "audit",
    "branch",
    "branches",
    "command",
    "commands",
    "duplicate",
    "execution",
    "feature",
    "features",
    "fix",
    "handler",
    "handlers",
    "implementation",
    "integration",
    "main",
    "provider",
    "refactor",
    "summary",
    "supervisor",
    "surface",
    "surfaces",
    "task",
    "tasks",
    "worktree",
    "worktrees",
    "worker",
    "workers",
}


def handle_worktree_audit_command(args: argparse.Namespace, *, api: Any) -> int:
    payload = worktree_audit_payload(args, api=api)
    if args.json:
        api._print_json(payload)
    else:
        print_worktree_audit_plain(payload)
    return 0


def worktree_audit_payload(
    args: argparse.Namespace,
    *,
    api: Any | None = None,
) -> dict[str, Any]:
    if api is None:
        from isotope.features.supervisor import runner as api

    repo_root = Path(args.repo_root).expanduser()
    completed = api.subprocess.run(
        ["git", "-C", str(repo_root), "worktree", "list", "--porcelain"],
        check=False,
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        return {
            "kind": "supervisor_worktree_audit",
            "status": "error",
            "repo_root": str(repo_root),
            "summary": {"worktrees": 0, "duplicate_candidates": 0},
            "worktrees": [],
            "duplicate_candidates": [],
            "error": (completed.stderr or completed.stdout or "").strip(),
        }
    records = parse_worktree_list_porcelain(completed.stdout)
    records = enrich_worktree_records_with_status(records, api=api)
    payload = audit_worktree_records(records)
    payload["repo_root"] = str(repo_root)
    return payload


def parse_worktree_list_porcelain(text: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            if current is not None:
                records.append(_finish_worktree_record(current))
                current = None
            continue
        key, _, value = line.partition(" ")
        if key == "worktree":
            if current is not None:
                records.append(_finish_worktree_record(current))
            current = {"path": value, "branch": None, "detached": False}
            continue
        if current is None:
            continue
        if key == "HEAD":
            current["head"] = value
        elif key == "branch":
            current["branch"] = _short_branch_name(value)
            current["detached"] = False
        elif key == "detached":
            current["detached"] = True
    if current is not None:
        records.append(_finish_worktree_record(current))
    return records


def audit_worktree_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    worktrees = [_worktree_payload(record) for record in records]
    duplicate_candidates = _duplicate_topic_candidates(worktrees)
    overlapping_modified_files = _overlapping_modified_files(worktrees)
    return {
        "kind": "supervisor_worktree_audit",
        "status": "attention"
        if duplicate_candidates or overlapping_modified_files
        else "ok",
        "summary": {
            "worktrees": len(worktrees),
            "dirty_worktrees": sum(1 for item in worktrees if item["dirty"]),
            "duplicate_candidates": len(duplicate_candidates),
            "overlapping_modified_files": len(overlapping_modified_files),
        },
        "worktrees": worktrees,
        "duplicate_candidates": duplicate_candidates,
        "overlapping_modified_files": overlapping_modified_files,
        "note": "audit report; no worktree, branch, or file is modified",
    }


def print_worktree_audit_plain(payload: dict[str, Any]) -> None:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    print("[Supervisor worktree audit]")
    print(f"status：{payload.get('status', '')}")
    if payload.get("repo_root"):
        print(f"repo：{payload['repo_root']}")
    print(
        "worktrees："
        f"{summary.get('worktrees', 0)} / dirty "
        f"{summary.get('dirty_worktrees', 0)} / duplicate candidates "
        f"{summary.get('duplicate_candidates', 0)} / overlapping files "
        f"{summary.get('overlapping_modified_files', 0)}"
    )
    overlaps = payload.get("overlapping_modified_files") or []
    for overlap in overlaps:
        files = ", ".join(overlap.get("files") or [])
        print(f"- overlapping files：{files}")
        for item in overlap.get("worktrees") or []:
            branch = item.get("branch") or "detached"
            print(f"  {branch} / {item.get('path', '')}")
    candidates = payload.get("duplicate_candidates") or []
    for candidate in candidates:
        shared = ", ".join(candidate.get("shared_tokens") or [])
        print(f"- shared topic：{shared}")
        for item in candidate.get("worktrees") or []:
            branch = item.get("branch") or "detached"
            print(f"  {branch} / {item.get('path', '')}")
    if not candidates:
        print("duplicate candidates：none")


def enrich_worktree_records_with_status(
    records: list[dict[str, Any]],
    *,
    api: Any,
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for record in records:
        item = dict(record)
        completed = api.subprocess.run(
            [
                "git",
                "-C",
                str(item.get("path") or ""),
                "status",
                "--porcelain=v1",
            ],
            check=False,
            text=True,
            capture_output=True,
        )
        if completed.returncode == 0:
            modified_files = parse_worktree_status_porcelain(completed.stdout)
            item["modified_files"] = modified_files
            item["dirty"] = bool(modified_files)
        else:
            item["modified_files"] = []
            item["dirty"] = False
            item["status_error"] = (completed.stderr or completed.stdout or "").strip()
        enriched.append(item)
    return enriched


def parse_worktree_status_porcelain(text: str) -> list[str]:
    paths: list[str] = []
    for raw_line in text.splitlines():
        if not raw_line:
            continue
        path = raw_line[3:] if len(raw_line) > 3 else ""
        path = path.strip()
        if " -> " in path:
            path = path.rsplit(" -> ", 1)[1]
        if path:
            paths.append(path)
    return sorted(dict.fromkeys(paths))


def _finish_worktree_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": record.get("path"),
        "head": record.get("head"),
        "branch": record.get("branch"),
        "detached": bool(record.get("detached")),
    }


def _short_branch_name(value: str) -> str:
    prefix = "refs/heads/"
    if value.startswith(prefix):
        return value[len(prefix) :]
    return value


def _worktree_payload(record: dict[str, Any]) -> dict[str, Any]:
    path = str(record.get("path") or "")
    branch = record.get("branch")
    text = branch if isinstance(branch, str) and branch else Path(path).name
    return {
        "path": path,
        "head": record.get("head"),
        "branch": branch,
        "detached": bool(record.get("detached")),
        "dirty": bool(record.get("dirty")),
        "modified_files": list(record.get("modified_files") or []),
        "status_error": record.get("status_error"),
        "topic_tokens": topic_tokens_for_text(text),
    }


def _is_primary_worktree(worktree: dict[str, Any]) -> bool:
    branch = worktree.get("branch")
    return branch in {"main", "master"}


def _duplicate_topic_candidates(worktrees: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for index, left in enumerate(worktrees):
        for right in worktrees[index + 1 :]:
            shared_tokens = sorted(
                set(left.get("topic_tokens") or []) & set(right.get("topic_tokens") or [])
            )
            if not shared_tokens:
                continue
            candidates.append(
                {
                    "kind": "shared_topic",
                    "severity": "attention",
                    "shared_tokens": shared_tokens,
                    "worktrees": [
                        _candidate_worktree_ref(left),
                        _candidate_worktree_ref(right),
                    ],
                }
            )
    return candidates


def _overlapping_modified_files(
    worktrees: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    overlaps: list[dict[str, Any]] = []
    for index, left in enumerate(worktrees):
        left_files = set(left.get("modified_files") or [])
        if not left_files:
            continue
        for right in worktrees[index + 1 :]:
            right_files = set(right.get("modified_files") or [])
            files = sorted(left_files & right_files)
            if not files:
                continue
            overlaps.append(
                {
                    "kind": "overlapping_modified_files",
                    "severity": "warning",
                    "files": files,
                    "worktrees": [
                        _candidate_worktree_ref(left),
                        _candidate_worktree_ref(right),
                    ],
                }
            )
    return overlaps


def _candidate_worktree_ref(worktree: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": worktree.get("path"),
        "branch": worktree.get("branch"),
        "head": worktree.get("head"),
        "detached": worktree.get("detached"),
    }


def topic_tokens_for_text(text: str) -> list[str]:
    tokens = [
        token
        for token in re.split(r"[^a-zA-Z0-9]+", text.lower())
        if len(token) >= 3 and token not in GENERIC_TOPIC_TOKENS
    ]
    return sorted(dict.fromkeys(tokens))
