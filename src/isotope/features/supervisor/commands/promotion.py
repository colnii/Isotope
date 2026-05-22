"""Merge promotion command-loop handling for Supervisor."""

from __future__ import annotations

import argparse
import subprocess
from typing import Any


def auto_promote_done_merge_workers_to_main(
    args: argparse.Namespace,
    *,
    run: Any = subprocess.run,
    api: Any | None = None,
) -> list[dict[str, Any]]:
    if api is None:
        from isotope.features.supervisor import runner as api

    if getattr(args, "command", None) != "loop":
        return []
    if not getattr(args, "auto_merge_promote", False):
        return []
    if api._current_workspace_has_worker_role(args, api.RECURSIVE_WORKER_ROLES):
        return []
    repo_root = api._workspace_root(args) or api.Path.cwd()
    codex_home = api.Path(args.codex_home)
    review_payload = api.collect_integration_reviews(
        codex_home=codex_home,
        base_ref="main",
        include_unfinished=False,
    )
    groups = review_payload.get("groups")
    if not isinstance(groups, dict):
        return []
    promoted: list[dict[str, Any]] = []
    for item in api._review_group_items(groups, "merge_workers"):
        repair = api._auto_repair_blocked_merge_worker_review_item(
            item,
            args=args,
            codex_home=codex_home,
        )
        if repair is not None:
            promoted.append(repair)
            continue
        promotion = api._auto_promote_merge_worker_review_item(
            item,
            args=args,
            codex_home=codex_home,
            repo_root=repo_root,
            run=run,
            webhook_url=getattr(args, "webhook_url", None),
            webhook_secret=getattr(args, "webhook_secret", None),
        )
        if promotion is not None:
            promoted.append(promotion)
    return promoted
