"""Side-effect execution helpers for Supervisor LLM actions."""

from __future__ import annotations

import argparse
import re
import shlex
from pathlib import Path
from typing import Any


def worker_profile_from_args(args: argparse.Namespace, *, api: Any | None = None) -> str:
    if api is None:
        from isotope.features.supervisor import runner as api

    raw = getattr(args, "worker_profile", api.DEFAULT_WORKER_PROFILE)
    profile = raw if isinstance(raw, str) and raw else api.DEFAULT_WORKER_PROFILE
    if profile not in api.WORKER_PROFILE_DEFAULTS:
        supported = ", ".join(api.WORKER_PROFILE_CHOICES)
        raise ValueError(f"unsupported worker_profile: {profile}; allowed: {supported}")
    return profile


def worker_profile_for_action(
    args: argparse.Namespace,
    action: dict[str, Any],
    *,
    api: Any | None = None,
) -> str:
    if api is None:
        from isotope.features.supervisor import runner as api

    raw = action.get("worker_profile")
    if isinstance(raw, str) and raw:
        if raw not in api.WORKER_PROFILE_DEFAULTS:
            supported = ", ".join(api.WORKER_PROFILE_CHOICES)
            raise ValueError(f"unsupported worker_profile: {raw}; allowed: {supported}")
        return raw
    return worker_profile_from_args(args, api=api)


def worker_profile_defaults(profile: str, *, api: Any | None = None) -> dict[str, Any]:
    if api is None:
        from isotope.features.supervisor import runner as api

    defaults = api.WORKER_PROFILE_DEFAULTS.get(profile)
    if defaults is None:
        supported = ", ".join(api.WORKER_PROFILE_CHOICES)
        raise ValueError(f"unsupported worker_profile: {profile}; allowed: {supported}")
    return defaults


def worker_codex_model(
    args: argparse.Namespace,
    *,
    profile: str | None = None,
    api: Any | None = None,
) -> str | None:
    if api is None:
        from isotope.features.supervisor import runner as api

    if not hasattr(args, "worker_codex_model"):
        return None
    value = getattr(args, "worker_codex_model", None)
    if value is None:
        defaults = worker_profile_defaults(
            profile or worker_profile_from_args(args, api=api),
            api=api,
        )
        return str(defaults["model"])
    return value if isinstance(value, str) else None


def worker_codex_config(
    args: argparse.Namespace,
    *,
    profile: str | None = None,
    api: Any | None = None,
) -> tuple[str, ...]:
    if api is None:
        from isotope.features.supervisor import runner as api

    if not hasattr(args, "worker_codex_config"):
        return ()
    value = getattr(args, "worker_codex_config", None)
    if value is None:
        defaults = worker_profile_defaults(
            profile or worker_profile_from_args(args, api=api),
            api=api,
        )
        return tuple(defaults["config"])
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def execute_resume_action(
    args: argparse.Namespace,
    report: Any,
    action: dict[str, Any],
    *,
    api: Any | None = None,
) -> dict[str, Any]:
    if api is None:
        from isotope.features.supervisor import runner as api

    session_id = action.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("session_id is required for resume_session")
    target = api._target_session(report, session_id)
    if target is None or not api._is_resume_capable_session(target):
        raise ValueError(f"no resumable Codex session for: {session_id}")
    prompt_kind = action.get("prompt_kind") or "send_continue"
    if prompt_kind not in api.EXECUTABLE_ADVICE_KINDS:
        supported = ", ".join(sorted(api.EXECUTABLE_ADVICE_KINDS))
        raise ValueError(f"resume prompt_kind supports only: {supported}")
    prompt_text = api.EXECUTABLE_ADVICE_TEXT[str(prompt_kind)]
    suggestion = action.get("command_suggestion") or api._resume_session_command_suggestion(
        target,
        prompt_kind=str(prompt_kind),
    )
    target_name = action.get("target_name") or suggestion.get("target_name")
    if not isinstance(target_name, str) or not target_name:
        target_name = api._resume_managed_name_for_session(target)
    if running_record := running_managed_process_for_session(
        codex_home=Path(args.codex_home),
        session=target,
        api=api,
    ):
        return {
            "kind": "resume_session",
            "command": suggestion["command"],
            "skipped": True,
            "reason": "managed process already running",
            "managed": {
                "name": running_record.name,
                "record_id": running_record.record_id,
                "pid": running_record.pid,
                "backend": running_record.backend,
            },
        }
    if not cwd_is_existing_dir(target.cwd):
        return {
            "kind": "resume_session",
            "command": suggestion["command"],
            "skipped": True,
            "reason": "resume cwd missing",
            "cwd": target.cwd,
        }
    if prompt_kind == "send_continue":
        if budget_state := api.continue_budget_state(
            codex_home=Path(args.codex_home),
            name=target_name,
            max_continue_count=args.max_continue_count,
        ):
            return {
                "kind": "resume_session",
                "command": suggestion["command"],
                "skipped": True,
                "reason": "lane continue budget exhausted",
                "lane_state": budget_state.to_dict(),
            }
        if run_budget := api._run_budget_state(
            codex_home=Path(args.codex_home),
            name=target_name,
            max_run_minutes=args.max_run_minutes,
        ):
            return {
                "kind": "resume_session",
                "command": suggestion["command"],
                "skipped": True,
                "reason": "lane run budget exhausted",
                "run_budget": run_budget,
            }
    if cooldown_state := api.prompt_cooldown_state(
        codex_home=Path(args.codex_home),
        name=target_name,
        cooldown_seconds=args.prompt_cooldown,
    ):
        return {
            "kind": "resume_session",
            "command": suggestion["command"],
            "skipped": True,
            "reason": "resume prompt cooldown active",
            "lane_state": cooldown_state.to_dict(),
        }
    record = api.resume_managed_codex(
        codex_home=Path(args.codex_home),
        cwd=Path(target.cwd),
        name=target_name,
        prompt=prompt_text,
        session_id=session_id,
        codex_model=worker_codex_model(args, api=api),
        codex_config=worker_codex_config(args, api=api),
        popen=api.subprocess.Popen,
    )
    api.record_lane_prompt(
        codex_home=Path(args.codex_home),
        name=record.name,
        tmux_session=None,
        status=target.supervisor_status or target.status,
        prompt_kind=str(prompt_kind),
    )
    return {
        "kind": "resume_session",
        "command": suggestion["command"],
        "text": prompt_text,
        "managed": {
            "name": record.name,
            "record_id": record.record_id,
            "pid": record.pid,
            "backend": record.backend,
            "resume_session_id": record.resume_session_id,
        },
    }


def execute_launch_action(
    args: argparse.Namespace,
    action: dict[str, Any],
    *,
    api: Any | None = None,
) -> dict[str, Any]:
    if api is None:
        from isotope.features.supervisor import runner as api

    target_name = action.get("target_name")
    cwd = action.get("cwd")
    prompt = action.get("prompt")
    if not isinstance(target_name, str) or not target_name.strip():
        raise ValueError("target_name is required for launch_session")
    if not isinstance(cwd, str) or not cwd.strip():
        raise ValueError("cwd is required for launch_session")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt is required for launch_session")
    if failure_state := api.lane_failure_state(
        codex_home=Path(args.codex_home),
        name=target_name,
    ):
        return {
            "kind": "monitor",
            "skipped": True,
            "reason": "worker failure recorded",
            "degraded_from": "launch_session",
            "target_name": target_name,
            "lane_state": failure_state.to_dict(),
        }
    if run_budget := api._run_budget_state(
        codex_home=Path(args.codex_home),
        name=target_name,
        max_run_minutes=args.max_run_minutes,
    ):
        failure_state = api.record_lane_failure(
            codex_home=Path(args.codex_home),
            name=target_name,
            tmux_session=None,
            reason="timeout",
            stderr_summary="worker exceeded run budget",
        )
        return {
            "kind": "monitor",
            "skipped": True,
            "reason": "worker timeout recorded",
            "degraded_from": "launch_session",
            "target_name": target_name,
            "lane_state": failure_state.to_dict(),
            "run_budget": run_budget,
        }
    if not cwd_is_existing_dir(cwd):
        return {
            "kind": "launch_session",
            "skipped": True,
            "reason": "launch cwd missing",
            "cwd": cwd,
        }
    if running_record := running_managed_process_by_name(
        codex_home=Path(args.codex_home),
        name=target_name,
        api=api,
    ):
        return {
            "kind": "launch_session",
            "skipped": True,
            "reason": "managed process already running",
            "managed": {
                "name": running_record.name,
                "record_id": running_record.record_id,
                "pid": running_record.pid,
                "backend": running_record.backend,
            },
        }
    if cooldown_state := api.prompt_cooldown_state(
        codex_home=Path(args.codex_home),
        name=target_name,
        cooldown_seconds=args.prompt_cooldown,
    ):
        return {
            "kind": "launch_session",
            "skipped": True,
            "reason": "launch prompt cooldown active",
            "lane_state": cooldown_state.to_dict(),
        }
    coordination_preflight = api._launch_coordination_preflight(
        cwd=Path(cwd),
        target_name=target_name,
        goal=prompt,
    )
    if coordination_preflight.get("status") == "needs_user":
        return {
            "kind": "launch_session",
            "skipped": True,
            "reason": "coordination preflight needs user",
            "target_name": target_name,
            "coordination_preflight": coordination_preflight,
        }
    worktree = api._prepare_launch_worktree(cwd=Path(cwd), target_name=target_name)
    if worktree.get("failed"):
        return {
            "kind": "launch_session",
            "skipped": True,
            "reason": "worktree setup failed",
            "worktree": worktree,
        }
    worker_cwd = str(worktree["cwd"])
    worker_profile = worker_profile_for_action(args, action, api=api)
    worker_role = worker_role_for_launch_action(action, api=api)
    work_order_prompt = api.build_launch_work_order_prompt(
        target_name=target_name,
        cwd=worker_cwd,
        goal=prompt,
        allow_remote_push=worker_role == api.MERGE_DISPATCH_WORKER_ROLE,
    )
    command = shlex.join(
        [
            "isotope-supervisor",
            "launch",
            "--name",
            target_name,
            "--cwd",
            worker_cwd,
            "--prompt",
            work_order_prompt,
        ]
    )
    record = api.launch_managed_codex(
        codex_home=Path(args.codex_home),
        cwd=Path(worker_cwd),
        name=target_name,
        prompt=work_order_prompt,
        codex_model=worker_codex_model(args, profile=worker_profile, api=api),
        codex_config=worker_codex_config(args, profile=worker_profile, api=api),
        worker_role=worker_role,
        popen=api.subprocess.Popen,
        run=api.subprocess.run,
    )
    api.record_lane_prompt(
        codex_home=Path(args.codex_home),
        name=record.name,
        tmux_session=None,
        status="launch_session",
        prompt_kind="launch_session",
    )
    return {
        "kind": "launch_session",
        "command": command,
        "text": work_order_prompt,
        "worker_profile": worker_profile,
        "managed": {
            "name": record.name,
            "record_id": record.record_id,
            "pid": record.pid,
            "backend": record.backend,
            "worker_role": record.worker_role,
        },
        "worktree": worktree,
    }


def worker_role_for_launch_action(
    action: dict[str, Any],
    *,
    api: Any | None = None,
) -> str:
    if api is None:
        from isotope.features.supervisor import runner as api

    role = action.get("worker_role")
    if isinstance(role, str) and role.strip():
        return role.strip()
    if action.get("source") == "integration_review":
        return api.MERGE_DISPATCH_WORKER_ROLE
    return "worker"


def prepare_launch_worktree(
    *,
    cwd: Path,
    target_name: str,
    api: Any | None = None,
) -> dict[str, Any]:
    if api is None:
        from isotope.features.supervisor import runner as api

    source_cwd = cwd.expanduser()
    root = git_root_for_worktree(source_cwd, api=api)
    if root is None:
        return {
            "enabled": False,
            "source_cwd": str(source_cwd),
            "cwd": str(source_cwd),
            "reason": "not_git_repo",
        }
    suffix = api.uuid.uuid4().hex[:8]
    safe_name = safe_worktree_name(target_name)
    branch = f"supervisor/{safe_name}-{suffix}"
    worktree = root / ".worktrees" / "supervisor" / f"{safe_name}-{suffix}"
    worktree.parent.mkdir(parents=True, exist_ok=True)
    try:
        completed = api.subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "worktree",
                "add",
                "-b",
                branch,
                str(worktree),
                "HEAD",
            ],
            check=False,
            text=True,
            capture_output=True,
        )
    except (OSError, api.subprocess.SubprocessError, TypeError) as exc:
        return {
            "enabled": False,
            "failed": True,
            "source_cwd": str(source_cwd),
            "cwd": str(source_cwd),
            "worktree_root": str(worktree),
            "branch": branch,
            "reason": str(exc),
        }
    if completed.returncode != 0:
        return {
            "enabled": False,
            "failed": True,
            "source_cwd": str(source_cwd),
            "cwd": str(source_cwd),
            "worktree_root": str(worktree),
            "branch": branch,
            "reason": (completed.stderr or completed.stdout or "git worktree add failed").strip(),
        }
    worker_cwd = worktree / relative_cwd_in_repo(source_cwd, root)
    return {
        "enabled": True,
        "source_cwd": str(source_cwd),
        "cwd": str(worker_cwd),
        "worktree_root": str(worktree),
        "branch": branch,
    }


def git_root_for_worktree(cwd: Path, *, api: Any | None = None) -> Path | None:
    if api is None:
        from isotope.features.supervisor import runner as api

    try:
        completed = api.subprocess.run(
            ["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
            check=False,
            text=True,
            capture_output=True,
        )
    except (OSError, api.subprocess.SubprocessError, TypeError):
        return None
    if completed.returncode != 0:
        return None
    root = completed.stdout.strip()
    return Path(root) if root else None


def safe_worktree_name(name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", name.strip()).strip(".-_")
    return safe.lower() or "worker"


def relative_cwd_in_repo(cwd: Path, root: Path) -> Path:
    try:
        return cwd.resolve().relative_to(root.resolve())
    except ValueError:
        return Path()


def running_managed_process_by_name(
    *,
    codex_home: Path,
    name: str,
    api: Any | None = None,
) -> Any | None:
    if api is None:
        from isotope.features.supervisor import runner as api

    for record in reversed(api.read_managed_records(api.default_registry_path(codex_home))):
        if record.name != name:
            continue
        if record.backend == "tmux":
            continue
        if api._pid_is_running(record.pid):
            return record
    return None


def running_managed_process_for_session(
    *,
    codex_home: Path,
    session: Any,
    api: Any | None = None,
) -> Any | None:
    if api is None:
        from isotope.features.supervisor import runner as api

    session_id = getattr(session, "session_id", None)
    session_cwd = path_identity(getattr(session, "cwd", None))
    for record in reversed(api.read_managed_records(api.default_registry_path(codex_home))):
        if record.backend == "tmux":
            continue
        if not api._pid_is_running(record.pid):
            continue
        if isinstance(session_id, str) and record.resume_session_id == session_id:
            return record
        if session_cwd is not None and path_identity(record.cwd) == session_cwd:
            return record
    return None


def path_identity(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return str(Path(value).expanduser().resolve(strict=False))


def cwd_is_existing_dir(value: object) -> bool:
    return isinstance(value, str) and bool(value) and Path(value).expanduser().is_dir()


def execute_context_action(
    args: argparse.Namespace,
    action: dict[str, Any],
    *,
    api: Any | None = None,
) -> dict[str, Any]:
    if api is None:
        from isotope.features.supervisor import runner as api

    cwd = action.get("cwd")
    query = action.get("query")
    if not isinstance(cwd, str) or not cwd.strip():
        raise ValueError("cwd is required for request_context")
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query is required for request_context")
    suggestion = action.get("command_suggestion")
    command = (
        suggestion["command"]
        if isinstance(suggestion, dict) and isinstance(suggestion.get("command"), str)
        else shlex.join(
            [
                "isotope-supervisor",
                "context",
                "--cwd",
                cwd,
                "--query",
                query,
            ]
        )
    )
    if not cwd_is_existing_dir(cwd):
        return {
            "kind": "request_context",
            "command": command,
            "cwd": cwd,
            "query": query,
            "skipped": True,
            "reason": "request_context cwd missing",
        }
    result = api.CapabilityRunner().run_capability(
        "supervisor.request_context",
        inputs={
            "codex_home": str(Path(args.codex_home)),
            "cwd": cwd,
            "query": query,
        },
    )
    return {
        "kind": "request_context",
        "command": command,
        "cwd": cwd,
        "query": query,
        "context": context_from_capability_result(result),
    }


def context_from_capability_result(result: dict[str, Any]) -> dict[str, Any]:
    context_result = result.get("context_result")
    if not isinstance(context_result, dict):
        raise ValueError("supervisor.request_context did not return context_result")
    context = dict(context_result)
    context.pop("item_count", None)
    return context


def execute_ask_user_action(
    args: argparse.Namespace,
    action: dict[str, Any],
    *,
    api: Any | None = None,
) -> dict[str, Any]:
    if api is None:
        from isotope.features.supervisor import runner as api

    question = action.get("question")
    session_id = action.get("session_id")
    goal_id = action.get("goal_id")
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question is required for ask_user")
    if not isinstance(session_id, str) or not session_id.strip():
        session_id = (
            f"goal:{goal_id}"
            if isinstance(goal_id, str) and goal_id.strip()
            else None
        )
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("session_id is required for ask_user")
    gate = {
        "codex_requested_decision": action.get("codex_requested_decision"),
        "instructions_exhausted": action.get("instructions_exhausted"),
        "context_status": action.get("context_status"),
    }
    decision_request = api.record_decision_request(
        codex_home=Path(args.codex_home),
        action={**action, "session_id": session_id, "gate": gate},
        webhook_url=args.webhook_url,
        webhook_secret=args.webhook_secret,
    )
    return {
        "kind": "ask_user",
        "requires_user": True,
        "session_id": session_id,
        **({"goal_id": goal_id} if isinstance(goal_id, str) and goal_id else {}),
        "target_name": action.get("target_name"),
        "question": question,
        "reason": action["reason"],
        "context_status": action.get("context_status"),
        "gate": gate,
        "decision_request": decision_request.to_dict(),
    }
