"""Merge promotion command-loop handling for Supervisor."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from typing import Any


MERGE_REPAIR_WORKER_ROLE = "merge_repair"
MERGE_PROMOTION_DECISION_QUESTION = (
    "merge promotion 失败：是否修复 CI/工作区后重试，还是放弃本次 merge worker？"
)


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
        repair = auto_repair_blocked_merge_worker_review_item(
            item,
            args=args,
            codex_home=codex_home,
            api=api,
        )
        if repair is not None:
            promoted.append(repair)
            continue
        promotion = auto_promote_merge_worker_review_item(
            item,
            args=args,
            codex_home=codex_home,
            repo_root=repo_root,
            run=run,
            webhook_url=getattr(args, "webhook_url", None),
            webhook_secret=getattr(args, "webhook_secret", None),
            api=api,
        )
        if promotion is not None:
            promoted.append(promotion)
    return promoted


def auto_repair_blocked_merge_worker_review_item(
    item: dict[str, Any],
    *,
    args: argparse.Namespace,
    codex_home: Path,
    api: Any | None = None,
) -> dict[str, Any] | None:
    if api is None:
        from isotope.features.supervisor import runner as api

    if not api._merge_worker_review_item_is_blocked(item):
        return None
    name = _non_empty_text(item.get("name")) or api.MERGE_DISPATCH_TARGET_NAME
    record_id = _non_empty_text(item.get("record_id"))
    if not record_id:
        return None
    repair_name = f"{name}-repair"
    record = managed_record_by_id(codex_home=codex_home, record_id=record_id, api=api)
    if record is not None and record.backend != "tmux" and api._pid_is_running(record.pid):
        return {
            "kind": "merge_worker_conflict_repair",
            "name": name,
            "record_id": record_id,
            "status": "merge_worker_still_running",
        }
    if running_worker := api._running_managed_process_by_name(
        codex_home=codex_home,
        name=repair_name,
    ):
        return {
            "kind": "merge_worker_conflict_repair",
            "name": name,
            "record_id": record_id,
            "status": "repair_already_running",
            "repair": api._managed_worker_reference(running_worker),
        }
    if previous_repair := latest_managed_record_by_name(
        codex_home=codex_home,
        name=repair_name,
        api=api,
    ):
        protocol = api._supervisor_protocol_from_text(
            api._managed_process_log_excerpt(previous_repair.log_path) or ""
        )
        status = str(protocol.get("status") or "").strip().lower()
        if status in {"done", "blocked", "needs_user"}:
            return {
                "kind": "merge_worker_conflict_repair",
                "name": name,
                "record_id": record_id,
                "status": f"repair_{status}",
                "repair": api._managed_worker_reference(previous_repair),
            }
    if cooldown_state := api.prompt_cooldown_state(
        codex_home=codex_home,
        name=repair_name,
        cooldown_seconds=getattr(
            args,
            "prompt_cooldown",
            api.DEFAULT_PROMPT_COOLDOWN_SECONDS,
        ),
    ):
        return {
            "kind": "merge_worker_conflict_repair",
            "name": name,
            "record_id": record_id,
            "status": "repair_cooldown_active",
            "repair": {
                "kind": "launch_session",
                "skipped": True,
                "reason": "launch prompt cooldown active",
                "lane_state": cooldown_state.to_dict(),
            },
        }
    cwd = api._blocked_merge_worker_cwd(item, record=record)
    if cwd is None:
        return {
            "kind": "merge_worker_conflict_repair",
            "name": name,
            "record_id": record_id,
            "status": "repair_blocked",
            "reason": "merge worker cwd missing",
        }
    repair_prompt = api._merge_dispatch_conflict_repair_prompt(item=item, cwd=cwd)
    work_order_prompt = api.build_launch_work_order_prompt(
        target_name=repair_name,
        cwd=str(cwd),
        goal=repair_prompt,
        allow_remote_push=True,
    )
    launched = api.launch_managed_codex(
        codex_home=codex_home,
        cwd=cwd,
        name=repair_name,
        prompt=work_order_prompt,
        codex_model=api._worker_codex_model(args, profile=api.DEFAULT_WORKER_PROFILE),
        codex_config=api._worker_codex_config(args, profile=api.DEFAULT_WORKER_PROFILE),
        worker_role=MERGE_REPAIR_WORKER_ROLE,
        popen=subprocess.Popen,
        run=subprocess.run,
    )
    api.record_lane_prompt(
        codex_home=codex_home,
        name=launched.name,
        tmux_session=None,
        status="launch_session",
        prompt_kind="merge_conflict_repair",
    )
    return {
        "kind": "merge_worker_conflict_repair",
        "name": name,
        "record_id": record_id,
        "branch": _non_empty_text(item.get("branch")),
        "worker_commit": _non_empty_text(item.get("worker_commit")),
        "status": "repair_launched",
        "repair": {
            "kind": "launch_session",
            "target_name": repair_name,
            "worker_role": launched.worker_role,
            "text": work_order_prompt,
            "managed": {
                "name": launched.name,
                "record_id": launched.record_id,
                "pid": launched.pid,
                "backend": launched.backend,
                "worker_role": launched.worker_role,
            },
            "cwd": str(cwd),
        },
    }


def managed_record_by_id(
    *,
    codex_home: Path,
    record_id: str,
    api: Any | None = None,
) -> Any | None:
    if api is None:
        from isotope.features.supervisor import runner as api

    for record in reversed(api.read_managed_records(api.default_registry_path(codex_home))):
        if record.record_id == record_id:
            return record
    return None


def latest_managed_record_by_name(
    *,
    codex_home: Path,
    name: str,
    api: Any | None = None,
) -> Any | None:
    if api is None:
        from isotope.features.supervisor import runner as api

    for record in reversed(api.read_managed_records(api.default_registry_path(codex_home))):
        if record.name == name:
            return record
    return None


def auto_promote_merge_worker_review_item(
    item: dict[str, Any],
    *,
    args: argparse.Namespace,
    codex_home: Path,
    repo_root: Path,
    run: Any,
    webhook_url: str | None = None,
    webhook_secret: str | None = None,
    api: Any | None = None,
) -> dict[str, Any] | None:
    if api is None:
        from isotope.features.supervisor import runner as api

    if not api._merge_worker_review_item_is_done(item):
        return None
    if item.get("main_contains_worker") is True:
        return None
    name = _non_empty_text(item.get("name"))
    record_id = _non_empty_text(item.get("record_id"))
    branch = _non_empty_text(item.get("branch"))
    worker_commit = _non_empty_text(item.get("worker_commit"))
    if not name or not record_id or not branch or not worker_commit:
        return None
    answered_decision = merge_promotion_recent_decision_answer(
        codex_home=codex_home,
        record_id=record_id,
        api=api,
    )
    decision_intent = api._merge_promotion_decision_intent(answered_decision)
    repair_completed: dict[str, Any] | None = None
    if decision_intent == "abandon":
        return {
            "kind": "merge_worker_main_promotion",
            "name": name,
            "record_id": record_id,
            "branch": branch,
            "worker_commit": worker_commit,
            "status": "skipped_by_decision",
            "reason": "merge promotion abandoned by decision",
            "decision_answer": answered_decision,
        }
    if decision_intent == "repair":
        repair_completed = completed_merge_promotion_repair_worker(
            codex_home=codex_home,
            repair_name=f"{name}-repair",
            api=api,
        )
        if repair_completed is None:
            branch_ci = api._latest_ci_run_for_ref(
                branch=branch,
                commit=worker_commit,
                run=run,
            )
            return launch_merge_promotion_repair_worker(
                args=args,
                codex_home=codex_home,
                repo_root=repo_root,
                item=item,
                branch_ci=branch_ci,
                decision_answer=answered_decision,
                api=api,
            )
    branch_ci = api._latest_ci_run_for_ref(
        branch=branch,
        commit=worker_commit,
        run=run,
    )
    if not api._ci_run_succeeded(branch_ci, expected_commit=worker_commit):
        if api._ci_run_is_terminal(branch_ci):
            return blocked_merge_promotion(
                item,
                status_reason="branch CI did not succeed",
                branch_ci=branch_ci,
                codex_home=codex_home,
                webhook_url=webhook_url,
                webhook_secret=webhook_secret,
                api=api,
            )
        return {
            "kind": "merge_worker_main_promotion",
            "name": name,
            "record_id": record_id,
            "branch": branch,
            "worker_commit": worker_commit,
            "status": "waiting_for_branch_ci",
            "branch_ci": branch_ci,
        }
    precheck = api._check_main_promotion_preconditions(repo_root, run=run)
    if precheck is not None:
        return {
            "kind": "merge_worker_main_promotion",
            "name": name,
            "record_id": record_id,
            "branch": branch,
            "worker_commit": worker_commit,
            "status": "blocked",
            "reason": precheck,
            "branch_ci": branch_ci,
            "decision_request": merge_promotion_decision_request(
                codex_home=codex_home,
                item=item,
                reason=precheck,
                branch_ci=branch_ci,
                webhook_url=webhook_url,
                webhook_secret=webhook_secret,
                api=api,
            ),
        }
    merge_result = api._run_checked(
        ["git", "-C", str(repo_root), "merge", "--ff-only", worker_commit],
        run=run,
    )
    if merge_result is not None:
        return blocked_merge_promotion(
            item,
            status_reason=merge_result,
            branch_ci=branch_ci,
            codex_home=codex_home,
            webhook_url=webhook_url,
            webhook_secret=webhook_secret,
            api=api,
        )
    diff_result = api._run_checked(
        ["git", "-C", str(repo_root), "diff", "--check"],
        run=run,
    )
    if diff_result is not None:
        return blocked_merge_promotion(
            item,
            status_reason=diff_result,
            branch_ci=branch_ci,
            codex_home=codex_home,
            webhook_url=webhook_url,
            webhook_secret=webhook_secret,
            api=api,
        )
    push_result = api._run_checked(
        ["git", "-C", str(repo_root), "push", "origin", "main"],
        run=run,
    )
    if push_result is not None:
        return blocked_merge_promotion(
            item,
            status_reason=push_result,
            branch_ci=branch_ci,
            codex_home=codex_home,
            webhook_url=webhook_url,
            webhook_secret=webhook_secret,
            api=api,
        )
    main_head = api._git_text(repo_root, ["rev-parse", "HEAD"], run=run)
    if not main_head:
        main_head = worker_commit
    main_ci = api._latest_ci_run_for_ref(branch="main", commit=main_head, run=run)
    main_ci_run_id = main_ci.get("databaseId") if isinstance(main_ci, dict) else None
    if main_ci_run_id is not None:
        watch_result = api._run_checked(
            ["gh", "run", "watch", str(main_ci_run_id), "--exit-status"],
            run=run,
        )
        if watch_result is not None:
            return blocked_merge_promotion(
                item,
                status_reason=watch_result,
                branch_ci=branch_ci,
                main_ci=main_ci,
                main_head=main_head,
                codex_home=codex_home,
                webhook_url=webhook_url,
                webhook_secret=webhook_secret,
                api=api,
            )
        viewed = api._view_ci_run(str(main_ci_run_id), run=run)
        if viewed:
            main_ci = viewed
    if not api._ci_run_succeeded(main_ci, expected_commit=main_head):
        return blocked_merge_promotion(
            item,
            status_reason="main CI did not succeed",
            branch_ci=branch_ci,
            main_ci=main_ci,
            main_head=main_head,
            codex_home=codex_home,
            webhook_url=webhook_url,
            webhook_secret=webhook_secret,
            api=api,
        )
    payload = {
        "kind": "merge_worker_main_promotion",
        "name": name,
        "record_id": record_id,
        "branch": branch,
        "worker_commit": worker_commit,
        "status": "done",
        "main_head": main_head,
        "branch_ci": branch_ci,
        "main_ci": main_ci,
    }
    if repair_completed is not None:
        payload["repair_completed"] = archive_completed_merge_promotion_repair_worker(
            codex_home=codex_home,
            repair_completed=repair_completed,
            api=api,
        )
    return payload


def blocked_merge_promotion(
    item: dict[str, Any],
    *,
    status_reason: str,
    branch_ci: dict[str, Any],
    main_ci: dict[str, Any] | None = None,
    main_head: str | None = None,
    codex_home: Path | None = None,
    webhook_url: str | None = None,
    webhook_secret: str | None = None,
    api: Any | None = None,
) -> dict[str, Any]:
    if api is None:
        from isotope.features.supervisor import runner as api

    payload = {
        "kind": "merge_worker_main_promotion",
        "name": item.get("name"),
        "record_id": item.get("record_id"),
        "branch": item.get("branch"),
        "worker_commit": item.get("worker_commit"),
        "status": "blocked",
        "reason": status_reason,
        "branch_ci": branch_ci,
    }
    if main_ci is not None:
        payload["main_ci"] = main_ci
    if main_head is not None:
        payload["main_head"] = main_head
    if codex_home is not None:
        payload["decision_request"] = merge_promotion_decision_request(
            codex_home=codex_home,
            item=item,
            reason=status_reason,
            branch_ci=branch_ci,
            main_ci=main_ci,
            webhook_url=webhook_url,
            webhook_secret=webhook_secret,
            api=api,
        )
    return payload


def merge_promotion_decision_request(
    *,
    codex_home: Path,
    item: dict[str, Any],
    reason: str,
    branch_ci: dict[str, Any],
    main_ci: dict[str, Any] | None = None,
    webhook_url: str | None = None,
    webhook_secret: str | None = None,
    api: Any | None = None,
) -> dict[str, Any]:
    if api is None:
        from isotope.features.supervisor import runner as api

    record_id = _non_empty_text(item.get("record_id")) or "unknown"
    target_name = _non_empty_text(item.get("name"))
    branch = _non_empty_text(item.get("branch")) or "unknown"
    worker_commit = _non_empty_text(item.get("worker_commit")) or "unknown"
    for request in api.read_active_decision_requests(codex_home=codex_home, limit=1000):
        if (
            request.session_id == f"managed:{record_id}"
            and request.reason == "merge_promotion_failed"
            and request.question == MERGE_PROMOTION_DECISION_QUESTION
        ):
            return request.to_dict()
    action = {
        "kind": "ask_user",
        "session_id": f"managed:{record_id}",
        "target_name": target_name,
        "question": MERGE_PROMOTION_DECISION_QUESTION,
        "reason": "merge_promotion_failed",
        "context_status": "promotion_blocked",
        "gate": {
            "event_type": "merge_promotion_failed",
            "reason": reason,
            "branch": branch,
            "worker_commit": worker_commit,
            "branch_ci": branch_ci,
            "main_ci": main_ci,
        },
    }
    return api.record_decision_request(
        codex_home=codex_home,
        action=action,
        webhook_url=webhook_url,
        webhook_secret=webhook_secret,
    ).to_dict()


def launch_merge_promotion_repair_worker(
    *,
    args: argparse.Namespace,
    codex_home: Path,
    repo_root: Path,
    item: dict[str, Any],
    branch_ci: dict[str, Any],
    decision_answer: dict[str, Any] | None,
    api: Any | None = None,
) -> dict[str, Any]:
    if api is None:
        from isotope.features.supervisor import runner as api

    name = _non_empty_text(item.get("name")) or api.MERGE_DISPATCH_TARGET_NAME
    record_id = _non_empty_text(item.get("record_id")) or "unknown"
    branch = _non_empty_text(item.get("branch")) or "unknown"
    worker_commit = _non_empty_text(item.get("worker_commit")) or "unknown"
    repair_name = f"{name}-repair"
    if running_worker := api._running_managed_process_by_name(
        codex_home=codex_home,
        name=repair_name,
    ):
        return {
            "kind": "merge_worker_main_promotion",
            "name": name,
            "record_id": record_id,
            "branch": branch,
            "worker_commit": worker_commit,
            "status": "repair_already_running",
            "repair": api._managed_worker_reference(running_worker),
            "decision_answer": decision_answer,
        }
    if cooldown_state := api.prompt_cooldown_state(
        codex_home=codex_home,
        name=repair_name,
        cooldown_seconds=getattr(
            args,
            "prompt_cooldown",
            api.DEFAULT_PROMPT_COOLDOWN_SECONDS,
        ),
    ):
        return {
            "kind": "merge_worker_main_promotion",
            "name": name,
            "record_id": record_id,
            "branch": branch,
            "worker_commit": worker_commit,
            "status": "repair_cooldown_active",
            "repair": {
                "kind": "launch_session",
                "skipped": True,
                "reason": "launch prompt cooldown active",
                "lane_state": cooldown_state.to_dict(),
            },
            "decision_answer": decision_answer,
        }
    worktree = api._prepare_launch_worktree(cwd=repo_root, target_name=repair_name)
    if worktree.get("failed"):
        return {
            "kind": "merge_worker_main_promotion",
            "name": name,
            "record_id": record_id,
            "branch": branch,
            "worker_commit": worker_commit,
            "status": "repair_blocked",
            "repair": {
                "kind": "launch_session",
                "skipped": True,
                "reason": "worktree setup failed",
                "worktree": worktree,
            },
            "decision_answer": decision_answer,
        }
    repair_prompt = api._merge_promotion_repair_prompt(
        item=item,
        branch_ci=branch_ci,
        decision_answer=decision_answer,
    )
    worker_cwd = Path(str(worktree["cwd"]))
    work_order_prompt = api.build_launch_work_order_prompt(
        target_name=repair_name,
        cwd=str(worker_cwd),
        goal=repair_prompt,
        allow_remote_push=False,
    )
    record = api.launch_managed_codex(
        codex_home=codex_home,
        cwd=worker_cwd,
        name=repair_name,
        prompt=work_order_prompt,
        codex_model=api._worker_codex_model(args, profile=api.DEFAULT_WORKER_PROFILE),
        codex_config=api._worker_codex_config(args, profile=api.DEFAULT_WORKER_PROFILE),
        worker_role=MERGE_REPAIR_WORKER_ROLE,
        popen=subprocess.Popen,
        run=subprocess.run,
    )
    api.record_lane_prompt(
        codex_home=codex_home,
        name=record.name,
        tmux_session=None,
        status="launch_session",
        prompt_kind="merge_promotion_repair",
    )
    return {
        "kind": "merge_worker_main_promotion",
        "name": name,
        "record_id": record_id,
        "branch": branch,
        "worker_commit": worker_commit,
        "status": "repair_launched",
        "branch_ci": branch_ci,
        "decision_answer": decision_answer,
        "repair": {
            "kind": "launch_session",
            "target_name": repair_name,
            "worker_role": record.worker_role,
            "text": work_order_prompt,
            "managed": {
                "name": record.name,
                "record_id": record.record_id,
                "pid": record.pid,
                "backend": record.backend,
                "worker_role": record.worker_role,
            },
            "worktree": worktree,
        },
    }


def completed_merge_promotion_repair_worker(
    *,
    codex_home: Path,
    repair_name: str,
    api: Any | None = None,
) -> dict[str, Any] | None:
    if api is None:
        from isotope.features.supervisor import runner as api

    for record in reversed(api.read_managed_records(api.default_registry_path(codex_home))):
        if record.name != repair_name:
            continue
        if getattr(record, "worker_role", "worker") != MERGE_REPAIR_WORKER_ROLE:
            continue
        protocol = api._supervisor_protocol_from_text(
            api._managed_process_log_excerpt(record.log_path) or ""
        )
        status = str(protocol.get("status") or "").strip().lower()
        if status != "done":
            return None
        payload = {
            "status": "done",
            "managed": api._managed_worker_reference(record),
        }
        if summary := _non_empty_text(protocol.get("summary")):
            payload["summary"] = summary
        if next_step := _non_empty_text(protocol.get("next")):
            payload["next"] = next_step
        return payload
    return None


def archive_completed_merge_promotion_repair_worker(
    *,
    codex_home: Path,
    repair_completed: dict[str, Any],
    api: Any | None = None,
) -> dict[str, Any]:
    if api is None:
        from isotope.features.supervisor import runner as api

    managed = repair_completed.get("managed")
    if not isinstance(managed, dict):
        return repair_completed
    name = _non_empty_text(managed.get("name"))
    record_id = _non_empty_text(managed.get("record_id"))
    if not name or not record_id:
        return repair_completed
    archived = api.archive_managed_codex(
        codex_home=codex_home,
        name=name,
        record_id=record_id,
    )
    return {
        **repair_completed,
        "status": "archived",
        "managed": archived.to_dict(),
    }


def merge_promotion_recent_decision_answer(
    *,
    codex_home: Path,
    record_id: str,
    api: Any | None = None,
) -> dict[str, Any] | None:
    if api is None:
        from isotope.features.supervisor import runner as api

    session_id = f"managed:{record_id}"
    for answer in api.read_recent_decision_answers(codex_home=codex_home, limit=1000):
        if answer.get("session_id") != session_id:
            continue
        if answer.get("reason") == "merge_promotion_failed":
            return dict(answer)
        if answer.get("question") == MERGE_PROMOTION_DECISION_QUESTION:
            return dict(answer)
    return None


def _non_empty_text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None
