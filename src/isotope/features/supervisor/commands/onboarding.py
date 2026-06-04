"""Onboarding command payloads for the Supervisor CLI."""

from __future__ import annotations

import argparse
import shlex
from pathlib import Path
from typing import Any

from isotope.features.supervisor.adoption.tmux_discovery import discover_tmux_adopt_candidates


def _default_api() -> Any:
    from isotope.features.supervisor import runner as api

    return api


def start_here_payload(
    args: argparse.Namespace,
    *,
    api: Any | None = None,
) -> dict[str, Any]:
    cwd = str(Path(args.cwd).expanduser())
    codex_home = str(Path(args.codex_home).expanduser())
    goal = str(args.goal).strip()
    if not goal:
        raise ValueError("goal must not be empty")
    start_command = " && ".join(
        [
            shlex.join(["cd", cwd]),
            shlex.join(
                [
                    "isotope-supervisor",
                    "up",
                    "--codex-home",
                    codex_home,
                    "--goal",
                    goal,
                    "--goal-low-water",
                    "2",
                    "--goal-replenish-limit",
                    "2",
                    "--max-fanout-launches",
                    "2",
                    "--merge-dispatch-execute",
                    "--lifecycle-archive-execute",
                    "--auto-merge-promote",
                ]
            ),
        ]
    )
    commands = {
        "start": start_command,
        "open_web": shlex.join(
            [
                "isotope-supervisor",
                "web",
                "--codex-home",
                codex_home,
                "--host",
                str(args.host),
                "--port",
                str(args.port),
            ]
        ),
        "check_status": shlex.join(
            ["isotope-supervisor", "daemon", "status", "--codex-home", codex_home]
        ),
        "list_goals": shlex.join(
            ["isotope-supervisor", "goal", "list", "--codex-home", codex_home]
        ),
        "list_decisions": shlex.join(
            ["isotope-supervisor", "decision", "list", "--codex-home", codex_home]
        ),
        "trace": shlex.join(
            ["isotope-supervisor", "trace", "--codex-home", codex_home, "--json"]
        ),
        "stop": shlex.join(
            ["isotope-supervisor", "daemon", "stop", "--codex-home", codex_home]
        ),
    }
    return {
        "status": "ok",
        "workflow": {
            "cwd": cwd,
            "codex_home": codex_home,
            "goal": goal,
            "goal_low_water": 2,
            "goal_replenish_limit": 2,
            "max_fanout_launches": 2,
            "web_url": f"http://{args.host}:{args.port}",
        },
        "recommended_order": [
            "start",
            "open_web",
            "check_status",
            "send_feedback",
        ],
        "commands": commands,
        "what_to_expect": [
            "start 会启动或唤起后台 daemon，并把目标交给 Supervisor。",
            "后台 loop 会让 LLM 读当前文档，必要时补充目标并启动 worker。",
            "web 和 trace 用来观察 goal、worker、decision、merge、cleanup 停在哪一步。",
        ],
        "feedback_prompts": [
            "页面是否能看出哪些 worker 正在跑？",
            "lifecycle_trace.next_attention 是否符合你的直觉？",
            "如果它停住了，停在 goal、worker、decision、merge 还是 cleanup？",
        ],
    }


def print_start_here_plain(payload: dict[str, Any]) -> None:
    workflow = payload["workflow"]
    commands = payload["commands"]
    print("[Supervisor 从这里开始]")
    print(f"工作目录：{workflow['cwd']}")
    print(f"目标：{workflow['goal']}")
    print()
    print("1. 先启动后台 Supervisor：")
    print(commands["start"])
    print()
    print("2. 打开本地页面观察：")
    print(commands["open_web"])
    print(f"浏览器地址：{workflow['web_url']}")
    print()
    print("3. 需要命令行看状态时：")
    print(commands["check_status"])
    print(commands["list_goals"])
    print(commands["list_decisions"])
    print(commands["trace"])
    print()
    print("4. 给我反馈时，优先看这三点：")
    for item in payload["feedback_prompts"]:
        print(f"- {item}")
    print()
    print("5. 想停掉后台 Supervisor：")
    print(commands["stop"])


def guide_payload(
    args: argparse.Namespace,
    *,
    api: Any | None = None,
) -> dict[str, Any]:
    if api is None:
        api = _default_api()
    if args.interval <= 0:
        raise ValueError("interval must be positive")
    cwd = str(Path(args.cwd).expanduser())
    tmux_session = args.tmux_session or args.name
    worker_profile = api._worker_profile_from_args(args)
    worker_codex_model = api._worker_codex_model(args, profile=worker_profile)
    worker_codex_config = api._worker_codex_config(args, profile=worker_profile)
    worker_codex_args = guide_worker_codex_args(
        model=worker_codex_model,
        config=worker_codex_config,
    )
    commands = {
        "resume": shlex.join(
            [
                "isotope-supervisor",
                "resume",
                "--name",
                args.name,
                "--cwd",
                cwd,
                "--session-id",
                "<session-id>",
                "--prompt",
                args.prompt,
            ]
        ),
        "resume_last": shlex.join(
            [
                "isotope-supervisor",
                "resume",
                "--name",
                args.name,
                "--cwd",
                cwd,
                "--last",
                "--prompt",
                args.prompt,
            ]
        ),
        "launch_process": shlex.join(
            [
                "isotope-supervisor",
                "launch",
                "--name",
                args.name,
                "--cwd",
                cwd,
                "--prompt",
                args.prompt,
            ]
        ),
        "launch_tmux": shlex.join(
            [
                "isotope-supervisor",
                "launch",
                "--backend",
                "tmux",
                "--name",
                args.name,
                "--tmux-session",
                tmux_session,
                "--cwd",
                cwd,
                "--prompt",
                args.prompt,
            ]
        ),
        "launch": shlex.join(
            [
                "isotope-supervisor",
                "launch",
                "--backend",
                "tmux",
                "--name",
                args.name,
                "--tmux-session",
                tmux_session,
                "--cwd",
                cwd,
                "--prompt",
                args.prompt,
            ]
        ),
        "adopt": shlex.join(
            [
                "isotope-supervisor",
                "adopt",
                "--name",
                args.name,
                "--cwd",
                cwd,
                "--tmux-session",
                tmux_session,
            ]
        ),
        "supervise": shlex.join(
            [
                "isotope-supervisor",
                "loop",
                "--interval",
                str(args.interval),
                *worker_codex_args,
            ]
        ),
        "daemon": shlex.join(
            [
                "isotope-supervisor",
                "daemon",
                "start",
                "--interval",
                str(args.interval),
                *worker_codex_args,
            ]
        ),
        "web": shlex.join(["isotope-supervisor", "web"]),
        "attach": shlex.join(["tmux", "attach", "-t", tmux_session]),
        "archive": shlex.join(["isotope-supervisor", "archive", "--name", args.name]),
    }
    return {
        "status": "ok",
        "workflow": {
            "cwd": cwd,
            "lane_name": args.name,
            "tmux_session": tmux_session,
            "prompt": args.prompt,
            "interval": args.interval,
            "worker_profile": worker_profile,
            "worker_codex_model": worker_codex_model,
            "worker_codex_config": list(worker_codex_config),
        },
        "commands": commands,
    }


def guide_worker_codex_args(*, model: str | None, config: tuple[str, ...]) -> list[str]:
    args: list[str] = []
    if model:
        args.extend(["--worker-codex-model", model])
    for item in config:
        args.extend(["--worker-codex-config", item])
    return args


def print_guide_plain(payload: dict[str, Any]) -> None:
    workflow = payload["workflow"]
    commands = payload["commands"]
    print("[Codex Supervisor 使用入口]")
    print(f"工作目录：{workflow['cwd']}")
    print(f"托管名：{workflow['lane_name']}")
    print(f"tmux：{workflow['tmux_session']}")
    print()
    print("1. 恢复历史会话并发送新指令：")
    print(commands["resume"])
    print("最近会话可用：")
    print(commands["resume_last"])
    print()
    print("2. 需要开新会话时：")
    print(commands["launch_process"])
    print()
    print("3. 需要透明旁观同一个 TUI 时，才使用 tmux：")
    print(commands["launch_tmux"])
    print(commands["adopt"])
    print()
    print("4. 启动后台自动监督：")
    print(commands["daemon"])
    print("前台调试可用：")
    print(commands["supervise"])
    print()
    print("5. 需要观察细节时：")
    print(commands["web"])
    print(commands["attach"])
    print()
    print("6. 窗口不用再跟进时归档：")
    print(commands["archive"])


def discover_payload(
    args: argparse.Namespace,
    *,
    api: Any | None = None,
) -> dict[str, Any]:
    if api is None:
        api = _default_api()
    cwd = str(Path(args.cwd).expanduser())
    candidates = discover_tmux_adopt_candidates(
        cwd=cwd,
        include_all=args.include_all,
        run=api.subprocess.run,
    )
    payload = {
        "status": "ok",
        "cwd": cwd,
        "candidates": [candidate.to_dict() for candidate in candidates],
    }
    selected = selected_discover_candidate(args, candidates)
    if selected is None:
        return payload
    lane_name = args.name or selected.suggested_name
    record = api.adopt_tmux_session(
        codex_home=Path(args.codex_home),
        cwd=Path(selected.cwd),
        name=lane_name,
        tmux_session=selected.tmux_session,
        prompt=args.prompt,
        run=api.subprocess.run,
    )
    payload["adopted_candidate"] = selected.to_dict()
    payload["managed"] = record.to_dict()
    payload["next_commands"] = {
        "attach": selected.attach_command,
        "loop": "isotope-supervisor loop --interval 30",
        "archive": shlex.join(["isotope-supervisor", "archive", "--name", record.name]),
    }
    return payload


def auto_adopt_discovered_tmux_sessions(
    args: argparse.Namespace,
    *,
    api: Any | None = None,
) -> list[dict[str, str]]:
    if api is None:
        api = _default_api()
    if not getattr(args, "auto_adopt", False):
        return []
    known_tmux = known_managed_tmux_sessions(Path(args.codex_home), api=api)
    candidates = discover_tmux_adopt_candidates(
        cwd=Path.cwd(),
        include_all=False,
        run=api.subprocess.run,
    )
    adopted: list[dict[str, str]] = []
    for candidate in candidates:
        if candidate.tmux_session in known_tmux:
            continue
        record = api.adopt_tmux_session(
            codex_home=Path(args.codex_home),
            cwd=Path(candidate.cwd),
            name=candidate.suggested_name,
            tmux_session=candidate.tmux_session,
            run=api.subprocess.run,
        )
        known_tmux.add(candidate.tmux_session)
        adopted.append(
            {
                "name": record.name,
                "tmux_session": record.tmux_session or candidate.tmux_session,
                "cwd": record.cwd,
                "status": record.status,
            }
        )
    return adopted


def known_managed_tmux_sessions(
    codex_home: Path,
    *,
    api: Any | None = None,
) -> set[str]:
    if api is None:
        api = _default_api()
    return {
        record.tmux_session
        for record in api.read_managed_record_events(
            api.default_registry_path(codex_home)
        )
        if record.tmux_session
    }


def selected_discover_candidate(
    args: argparse.Namespace,
    candidates: tuple[Any, ...],
) -> Any | None:
    if args.adopt_index is not None and args.adopt_first:
        raise ValueError("adopt-index and adopt-first cannot be used together")
    if args.adopt_first:
        if not candidates:
            raise ValueError("no discover candidate to adopt")
        return candidates[0]
    if args.adopt_index is None:
        return None
    if args.adopt_index <= 0:
        raise ValueError("adopt-index must be positive")
    index = args.adopt_index - 1
    if index >= len(candidates):
        raise ValueError(
            f"adopt-index out of range: {args.adopt_index} > {len(candidates)}"
        )
    return candidates[index]


def print_discover_plain(payload: dict[str, Any]) -> None:
    print("[Codex Supervisor tmux 发现]")
    print(f"工作目录：{payload['cwd']}")
    if managed := payload.get("managed"):
        candidate = payload["adopted_candidate"]
        print(f"已接管：{managed['name']} / tmux={candidate['tmux_session']}")
        next_commands = payload["next_commands"]
        print(f"打开：{next_commands['attach']}")
        print(f"监督：{next_commands['loop']}")
        print(f"归档：{next_commands['archive']}")
        return
    candidates = payload["candidates"]
    if not candidates:
        print("没有发现可接管的 Codex tmux 窗口。")
        return
    for index, item in enumerate(candidates, start=1):
        marker = "Codex" if item["looks_like_codex"] else "普通 tmux"
        print(
            f"{index}. {item['tmux_session']} / {marker} / cwd={item['cwd']} / "
            f"建议名={item['suggested_name']}"
        )
        print(f"   接管：{item['adopt_command']}")
        print(f"   打开：{item['attach_command']}")
