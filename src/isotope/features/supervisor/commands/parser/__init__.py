"""Argument parser registration for the Supervisor CLI."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from isotope.features.supervisor.commands.parser.common import (
    add_failure_retry_args as _add_failure_retry_args,
    add_goal_replenishment_args as _add_goal_replenishment_args,
    add_state_root_arg as _add_state_root_arg,
    add_webhook_args as _add_webhook_args,
)
from isotope.features.supervisor.commands.parser.agent_group import (
    add_agent_group_command_parser,
)
from isotope.features.supervisor.commands.parser.daemon import add_daemon_command_parser
from isotope.features.supervisor.commands.parser.loop import add_loop_command_parsers
from isotope.features.supervisor.commands.parser.memory import add_memory_command_parsers


def build_parser(*, api: Any | None = None) -> argparse.ArgumentParser:
    """Build the Supervisor CLI parser with defaults from the runner API surface."""
    if api is None:
        from isotope.features.supervisor import runner as api

    return _build_parser_impl(api=api)


def _build_parser_impl(*, api: Any) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage local Isotope Supervisor state.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command, help_text in (
        ("scan", "Print one Supervisor session report."),
        ("dashboard", "Print one grouped supervisor dashboard."),
        ("watch", "Print reports repeatedly."),
        ("advise", "Print one compact next-action suggestion."),
        ("supervise", "Run repeated reports with advice, optional LLM summary, and send execution."),
    ):
        subparser = subparsers.add_parser(command, help=help_text)
        _add_state_root_arg(subparser)
        subparser.add_argument("--limit", type=int, default=10, help="Maximum sessions.")
        subparser.add_argument(
            "--stale-after",
            type=int,
            default=600,
            help="Seconds without events before marking a session stale.",
        )
        subparser.add_argument(
            "--active-within",
            type=int,
            default=180,
            help="Seconds with recent events before marking a session working.",
        )
        subparser.add_argument("--json", action="store_true", help="Print JSON output.")
        subparser.add_argument(
            "--llm-summary",
            action="store_true",
            help="Use configured LLM to add a compact Chinese summary.",
        )
        subparser.add_argument(
            "--workspace-root",
            help="Limit LLM/action candidates to this workspace. Defaults to cwd.",
        )
        subparser.add_argument(
            "--all-workspaces",
            action="store_true",
            help="Let LLM/action candidates span every discovered workspace.",
        )
        if command == "supervise":
            _add_webhook_args(subparser)
    state_parser = subparsers.add_parser(
        "state",
        help="Print the unified public Supervisor state projection.",
    )
    _add_state_root_arg(state_parser)
    state_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    worktree_audit_parser = subparsers.add_parser(
        "worktree-audit",
        help="Warn about local worktrees that appear to share a development topic.",
    )
    worktree_audit_parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root or subdirectory to inspect. Defaults to cwd.",
    )
    worktree_audit_parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON output.",
    )
    for command in ("advise", "supervise"):
        subparsers.choices[command].add_argument(
            "--name",
            help="Target one managed lane by name for suggestions or execution.",
        )
        subparsers.choices[command].add_argument(
            "--goal",
            help="User goal for the LLM planner when it may need to launch a new worker.",
        )
        subparsers.choices[command].add_argument(
            "--execute",
            help="Execute one generated send suggestion. Supports send_status or send_continue.",
        )
        subparsers.choices[command].add_argument(
            "--llm-action",
            action="store_true",
            help="Ask configured LLM to choose one whitelist action without executing it.",
        )
        subparsers.choices[command].add_argument(
            "--llm-execute",
            action="store_true",
            help="Execute one LLM-chosen whitelist send action, or skip monitor.",
        )
        if command == "supervise":
            subparsers.choices[command].add_argument(
                "--capacity-decisions",
                action="store_true",
                help=(
                    "Plan one capacity decision for the current goal and pass it "
                    "to the LLM planner."
                ),
            )
        subparsers.choices[command].add_argument(
            "--prompt-cooldown",
            type=int,
            default=api.DEFAULT_PROMPT_COOLDOWN_SECONDS,
            help="Seconds before repeating send_status/send_continue for the same lane.",
        )
        subparsers.choices[command].add_argument(
            "--max-continue-count",
            type=int,
            default=api.DEFAULT_MAX_CONTINUE_COUNT,
            help="Maximum consecutive send_continue prompts for the same lane status. Default 0 disables.",
        )
        subparsers.choices[command].add_argument(
            "--max-context-requests",
            type=int,
            default=api.DEFAULT_MAX_CONTEXT_REQUESTS,
            help="Maximum request_context executions per supervise iteration. Default 0 disables.",
        )
        if command == "supervise":
            _add_failure_retry_args(subparsers.choices[command], api=api)
        subparsers.choices[command].add_argument(
            "--max-run-minutes",
            type=int,
            default=api.DEFAULT_MAX_RUN_MINUTES,
            help="Maximum elapsed minutes before send_continue is blocked for a lane. Default 0 disables.",
        )
        subparsers.choices[command].add_argument(
            "--max-fanout-launches",
            type=int,
            default=api.DEFAULT_FANOUT_LIMIT,
            help="Maximum launch_session actions fanout may execute in one iteration.",
        )
        if command == "supervise":
            subparsers.choices[command].add_argument(
                "--max-worker-retry-count",
                type=int,
                default=api.DEFAULT_MAX_WORKER_RETRY_COUNT,
                help=(
                    "Maximum automatic restarts for an exited process worker. "
                    "Default 2."
                ),
            )
        subparsers.choices[command].add_argument(
            "--worker-profile",
            choices=api.WORKER_PROFILE_CHOICES,
            default=api.DEFAULT_WORKER_PROFILE,
            help="Worker profile for launched Codex workers.",
        )
        subparsers.choices[command].add_argument(
            "--worker-codex-model",
            help="Pass -m/--model to Codex workers launched by LLM execution.",
        )
        subparsers.choices[command].add_argument(
            "--worker-codex-config",
            action="append",
            default=None,
            help="Pass one -c key=value override to Codex workers. Repeatable.",
        )
    for command in ("watch", "supervise"):
        command_parser = subparsers.choices[command]
        command_parser.add_argument(
            "--interval",
            type=int,
            default=180,
            help="Seconds between reports.",
        )
        command_parser.add_argument(
            "--iterations",
            type=int,
            help="Stop after this many reports. Omit to watch until interrupted.",
        )
        command_parser.add_argument(
            "--changes-only",
            action="store_true",
            help="Print only when session state changes.",
        )
    subparsers.choices["watch"].add_argument(
        "--bell",
        action="store_true",
        help="Write a terminal bell when a printed report needs attention.",
    )
    subparsers.choices["supervise"].add_argument(
        "--auto-execute",
        action="store_true",
        help="Use the rule-based auto policy to execute one whitelist action per loop.",
    )
    subparsers.choices["supervise"].add_argument(
        "--auto-adopt",
        action="store_true",
        help="Automatically adopt newly discovered Codex-like tmux sessions before each loop.",
    )
    subparsers.choices["supervise"].add_argument(
        "--bell",
        action="store_true",
        help="Write a terminal bell when a supervise iteration still needs human attention.",
    )
    add_loop_command_parsers(subparsers, api=api)
    for check_command, help_text in (
        (
            "check",
            "Print one read-only morning summary across daemon, goals, review, and cleanup.",
        ),
        (
            "overnight-check",
            "Alias for check; useful after an overnight Supervisor run.",
        ),
    ):
        check_parser = subparsers.add_parser(check_command, help=help_text)
        _add_state_root_arg(check_parser)
        check_parser.add_argument(
            "--base",
            default="main",
            help="Base branch/ref for integration-review. Defaults to main.",
        )
        check_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    add_daemon_command_parser(subparsers, api=api)
    web_parser = subparsers.add_parser("web", help="Serve a local Supervisor dashboard page.")
    _add_state_root_arg(web_parser)
    web_parser.add_argument("--limit", type=int, default=10, help="Maximum sessions.")
    web_parser.add_argument(
        "--stale-after",
        type=int,
        default=600,
        help="Seconds without events before marking a session stale.",
    )
    web_parser.add_argument(
        "--active-within",
        type=int,
        default=180,
        help="Seconds with recent events before marking a session working.",
    )
    web_parser.add_argument("--host", default="127.0.0.1", help="Bind host.")
    web_parser.add_argument("--port", type=int, default=8765, help="Bind port.")
    web_parser.add_argument(
        "--print-url",
        action="store_true",
        help="Print the local URL and exit without starting the server.",
    )
    launch_parser = subparsers.add_parser("launch", help="Launch and register a Codex process.")
    _add_state_root_arg(launch_parser)
    launch_parser.add_argument("--cwd", required=True, help="Workspace directory for Codex.")
    launch_parser.add_argument("--name", required=True, help="Managed lane name.")
    launch_parser.add_argument("--prompt", required=True, help="Initial Codex prompt.")
    launch_parser.add_argument(
        "--codex-bin",
        default="codex",
        help="Codex executable name or path.",
    )
    launch_parser.add_argument(
        "--codex-model",
        help="Pass -m/--model to the launched Codex worker.",
    )
    launch_parser.add_argument(
        "--codex-config",
        action="append",
        default=[],
        help="Pass one -c key=value override to the launched Codex worker. Repeatable.",
    )
    launch_parser.add_argument(
        "--backend",
        choices=("process", "tmux"),
        default="process",
        help="Launch backend.",
    )
    launch_parser.add_argument(
        "--tmux-session",
        help="tmux session name when --backend tmux is used. Defaults to --name.",
    )
    launch_parser.add_argument(
        "--worker-role",
        default="worker",
        help="Worker role stored in the managed registry. Defaults to worker.",
    )
    launch_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    worker_review_parser = subparsers.add_parser(
        "worker-review",
        help="Summarize Supervisor-managed workers for human review.",
    )
    _add_state_root_arg(worker_review_parser)
    worker_review_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    add_agent_group_command_parser(subparsers)
    add_memory_command_parsers(subparsers)
    integration_review_parser = subparsers.add_parser(
        "integration-review",
        help="Group managed workers by read-only integration readiness.",
    )
    _add_state_root_arg(integration_review_parser)
    integration_review_parser.add_argument(
        "--base",
        default="main",
        help="Base branch/ref to check containment against. Defaults to main.",
    )
    integration_review_parser.add_argument(
        "--include-unfinished",
        action="store_true",
        help="Also include non-done managed workers. Defaults to integration-ready done workers only.",
    )
    integration_review_parser.add_argument(
        "--include-missing-worktrees",
        action="store_true",
        help="Also include stale records whose worktree is already missing.",
    )
    integration_review_parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON output.",
    )
    _add_webhook_args(integration_review_parser)
    merge_work_order_parser = subparsers.add_parser(
        "merge-work-order",
        help="Build a read-only merge work order from integration-review.",
    )
    _add_state_root_arg(merge_work_order_parser)
    merge_work_order_parser.add_argument(
        "--base",
        default="main",
        help="Base branch/ref to check containment against. Defaults to main.",
    )
    merge_work_order_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    replan_parser = subparsers.add_parser(
        "replan",
        help="Build read-only next-round advice from worker-review candidates.",
    )
    _add_state_root_arg(replan_parser)
    replan_parser.add_argument(
        "--base",
        default="main",
        help="Base branch/ref to check integration readiness against. Defaults to main.",
    )
    replan_parser.add_argument(
        "--include-unfinished",
        action="store_true",
        help="Also include non-done workers in the integration-review input.",
    )
    replan_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    context_parser = subparsers.add_parser(
        "context",
        help="Search project context and record the result for the LLM planner.",
    )
    _add_state_root_arg(context_parser)
    context_parser.add_argument("--cwd", required=True, help="Workspace directory.")
    context_parser.add_argument("--query", required=True, help="Context search query.")
    context_parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum context snippets.",
    )
    context_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    research_parser = subparsers.add_parser(
        "research",
        help="Run delegated research through the shared research flow.",
    )
    research_parser.add_argument(
        "research_action",
        nargs="?",
        choices=("search", "list", "inspect", "providers", "promote"),
        default="search",
        help="Research action. Defaults to search for compatibility.",
    )
    research_parser.add_argument("--root", required=True, help="Runtime root directory.")
    research_parser.add_argument("--query", help="Research query.")
    research_parser.add_argument(
        "--provider",
        default="codex",
        choices=api.research_provider_choices(),
        help="Research provider.",
    )
    research_parser.add_argument(
        "--workspace-root",
        help="Workspace root for Codex delegated research. Defaults to current directory.",
    )
    research_parser.add_argument(
        "--codex-executable",
        default="codex",
        help="Codex CLI executable for --provider codex.",
    )
    research_parser.add_argument("--codex-home", help="Codex home for --provider codex.")
    research_parser.add_argument("--model", help="Codex model for --provider codex.")
    research_parser.add_argument(
        "--tavily-api-key",
        help="Tavily API key for --provider tavily.",
    )
    research_parser.add_argument(
        "--tavily-config",
        help="Private Tavily TOML config path. Defaults to research_tavily.toml.",
    )
    research_parser.add_argument(
        "--tavily-enable-network",
        action="store_true",
        help="Allow --provider tavily to make a real Tavily API request.",
    )
    research_parser.add_argument(
        "--tavily-timeout-seconds",
        type=int,
        default=30,
        help="Tavily request timeout for future Tavily execution.",
    )
    research_parser.add_argument(
        "--tavily-max-results",
        type=int,
        default=5,
        help="Maximum Tavily results requested by future Tavily execution.",
    )
    research_parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=120,
        help="Codex delegated research timeout in seconds.",
    )
    research_parser.add_argument(
        "--max-attempts",
        type=int,
        default=2,
        help="Maximum Codex delegated provider attempts for retryable failures.",
    )
    research_parser.add_argument(
        "--artifact-type",
        help="Filter list output by exact research artifact type, such as research.provider_trace.",
    )
    research_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of research artifacts to list.",
    )
    research_parser.add_argument("--run-id", help="Run id for research inspect.")
    research_parser.add_argument("--artifact-id", help="Artifact id for research inspect.")
    research_parser.add_argument("--agent-id", help="Agent id for research promote.")
    research_parser.add_argument("--thread-id", help="Thread id for research promote.")
    research_parser.add_argument(
        "--scope",
        choices=("thread", "run", "session"),
        default="run",
        help="Memory promotion scope for research promote. Defaults to run.",
    )
    research_parser.add_argument(
        "--quality",
        default="candidate",
        help="Memory candidate quality label for research promote.",
    )
    research_parser.add_argument("--proposal-id", help="Optional stable proposal id.")
    research_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    screen_parser = subparsers.add_parser(
        "screen",
        help="Inspect or summarize screen artifacts through the shared screen report boundary.",
    )
    screen_parser.add_argument(
        "screen_action",
        choices=("report", "inspect"),
        help="Screen artifact action.",
    )
    screen_parser.add_argument("--root", required=True, help="Runtime root directory.")
    screen_parser.add_argument("--run-id", required=True, help="Run id for screen artifacts.")
    screen_parser.add_argument("--artifact-id", help="Artifact id for screen inspect.")
    screen_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    capacity_parser = subparsers.add_parser(
        "capacity",
        help="Plan one low-risk Supervisor capacity call.",
    )
    capacity_subparsers = capacity_parser.add_subparsers(
        dest="capacity_command",
        required=True,
    )
    capacity_plan_parser = capacity_subparsers.add_parser(
        "plan",
        help="Ask LLM capacity calling to select one capability.",
    )
    capacity_plan_parser.add_argument("--goal", required=True, help="Capacity planning goal.")
    capacity_plan_parser.add_argument(
        "--state-root",
        help="State root for optional agent-loop execution. Defaults to ~/.codex.",
    )
    capacity_plan_parser.add_argument(
        "--execute-agent-loop",
        action="store_true",
        help="Execute the selected allowlisted capability through the agent loop.",
    )
    capacity_plan_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    decision_parser = subparsers.add_parser(
        "decision",
        help="List or archive Supervisor decision requests.",
    )
    decision_subparsers = decision_parser.add_subparsers(
        dest="decision_command",
        required=True,
    )
    for decision_command, help_text in (
        ("list", "List active decision requests."),
        ("archive", "Archive one handled decision request."),
        ("answer", "Record a user answer for one decision request."),
    ):
        command_parser = decision_subparsers.add_parser(
            decision_command,
            help=help_text,
        )
        _add_state_root_arg(command_parser)
        command_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    decision_subparsers.choices["archive"].add_argument(
        "--request-id",
        required=True,
        help="Decision request id to archive.",
    )
    decision_subparsers.choices["answer"].add_argument(
        "--request-id",
        required=True,
        help="Decision request id to answer.",
    )
    decision_subparsers.choices["answer"].add_argument(
        "--answer",
        required=True,
        help="User decision answer.",
    )
    _add_webhook_args(decision_subparsers.choices["answer"])
    goal_parser = subparsers.add_parser(
        "goal",
        help="Add, list, or archive persistent Supervisor goals.",
    )
    goal_subparsers = goal_parser.add_subparsers(
        dest="goal_command",
        required=True,
    )
    goal_add_parser = goal_subparsers.add_parser(
        "add",
        help="Add one persistent goal for the Supervisor loop.",
    )
    goal_add_parser.add_argument(
        "goal_text",
        nargs="?",
        help="Goal text. Positional form for one-sentence goal entry.",
    )
    _add_state_root_arg(goal_add_parser)
    goal_add_parser.add_argument(
        "--cwd",
        default=str(Path.cwd()),
        help="Workspace directory for this goal. Defaults to the current directory.",
    )
    goal_add_parser.add_argument("--goal", help="Goal text. Kept for compatibility.")
    goal_add_parser.add_argument(
        "--target-name",
        help="Preferred managed worker name. Defaults to the generated goal id.",
    )
    goal_add_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    goal_plan_parser = goal_subparsers.add_parser(
        "plan",
        help="Use LLM to propose a small batch of Supervisor goals.",
    )
    goal_plan_parser.add_argument(
        "goal_text",
        nargs="?",
        help="Optional high-level user goal to seed planning.",
    )
    _add_state_root_arg(goal_plan_parser)
    goal_plan_parser.add_argument(
        "--cwd",
        default=str(Path.cwd()),
        help="Workspace directory whose current docs seed planning.",
    )
    goal_plan_parser.add_argument(
        "--limit",
        type=int,
        default=3,
        help="Maximum goal candidates to return or write.",
    )
    goal_plan_parser.add_argument(
        "--write",
        action="store_true",
        help="Write generated candidates into the persistent goal queue.",
    )
    goal_plan_parser.add_argument(
        "--fanout-execute",
        action="store_true",
        help="After --write, execute parallel_recommendations as controlled launch_session actions.",
    )
    goal_plan_parser.add_argument(
        "--max-fanout-launches",
        type=int,
        default=api.DEFAULT_FANOUT_LIMIT,
        help="Maximum launch_session actions fanout may execute for this plan.",
    )
    goal_plan_parser.add_argument(
        "--prompt-cooldown",
        type=int,
        default=api.DEFAULT_PROMPT_COOLDOWN_SECONDS,
        help="Seconds before repeating launch_session for the same lane.",
    )
    goal_plan_parser.add_argument(
        "--max-run-minutes",
        type=int,
        default=api.DEFAULT_MAX_RUN_MINUTES,
        help="Maximum elapsed minutes before launch_session is blocked for a lane. Default 0 disables.",
    )
    goal_plan_parser.add_argument(
        "--worker-profile",
        choices=api.WORKER_PROFILE_CHOICES,
        default=api.DEFAULT_WORKER_PROFILE,
        help="Worker profile for Codex workers launched by fanout.",
    )
    goal_plan_parser.add_argument(
        "--worker-codex-model",
        help="Pass -m/--model to Codex workers launched by fanout.",
    )
    goal_plan_parser.add_argument(
        "--worker-codex-config",
        action="append",
        default=None,
        help="Pass one -c key=value override to Codex workers. Repeatable.",
    )
    goal_plan_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    for goal_command, help_text in (
        ("list", "List active Supervisor goals."),
        ("archive", "Archive one handled Supervisor goal."),
    ):
        goal_command_parser = goal_subparsers.add_parser(goal_command, help=help_text)
        _add_state_root_arg(goal_command_parser)
        goal_command_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    goal_subparsers.choices["archive"].add_argument(
        "--goal-id",
        required=True,
        help="Supervisor goal id to archive.",
    )
    goal_subparsers.choices["archive"].add_argument(
        "--status",
        choices=sorted(api.GOAL_STATUS_VALUES),
        help="Optional final Supervisor status to store on the archive event.",
    )
    goal_subparsers.choices["archive"].add_argument(
        "--summary",
        help="Optional completion summary to store on the archive event.",
    )
    goal_subparsers.choices["archive"].add_argument(
        "--next-step",
        help="Optional next step to store as next on the archive event.",
    )
    cleanup_parser = subparsers.add_parser(
        "cleanup",
        help="List or archive completed Supervisor lifecycle items.",
    )
    cleanup_subparsers = cleanup_parser.add_subparsers(
        dest="cleanup_command",
        required=True,
    )
    for cleanup_command, help_text in (
        ("list", "List completed goals, managed workers, and notifications."),
        ("archive", "Archive completed lifecycle items without deleting Codex history."),
        ("delete-worktree", "Remove one archived and integrated Supervisor worktree."),
    ):
        cleanup_command_parser = cleanup_subparsers.add_parser(
            cleanup_command,
            help=help_text,
        )
        _add_state_root_arg(cleanup_command_parser)
        cleanup_command_parser.add_argument(
            "--json",
            action="store_true",
            help="Print JSON output.",
        )
    cleanup_archive_parser = cleanup_subparsers.choices["archive"]
    cleanup_target = cleanup_archive_parser.add_mutually_exclusive_group(required=True)
    cleanup_target.add_argument(
        "--all",
        action="store_true",
        help="Archive every currently listed cleanup candidate.",
    )
    cleanup_target.add_argument("--goal-id", help="Archive one completed goal.")
    cleanup_target.add_argument("--name", help="Archive one completed managed worker.")
    cleanup_target.add_argument(
        "--notification-id",
        help="Mark one completed Supervisor notification as read.",
    )
    cleanup_archive_parser.add_argument(
        "--record-id",
        help="When archiving by --name, target one managed record id.",
    )
    cleanup_delete_worktree_parser = cleanup_subparsers.choices["delete-worktree"]
    cleanup_delete_worktree_parser.add_argument(
        "--name",
        required=True,
        help="Managed worker name whose worktree should be removed.",
    )
    cleanup_delete_worktree_parser.add_argument(
        "--record-id",
        help="Managed record id to guard against deleting a newer worker.",
    )
    cleanup_delete_worktree_parser.add_argument(
        "--base",
        default="main",
        help="Base ref used for integration confirmation. Defaults to main.",
    )
    cleanup_delete_worktree_parser.add_argument(
        "--confirm-delete-worktree",
        action="store_true",
        help="Required confirmation before removing the worktree.",
    )
    trace_parser = subparsers.add_parser(
        "trace",
        help="Print a read-only Supervisor lifecycle trace.",
    )
    _add_state_root_arg(trace_parser)
    trace_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    resume_parser = subparsers.add_parser(
        "resume",
        help="Resume a Codex session with a prompt and register the managed process.",
    )
    _add_state_root_arg(resume_parser)
    resume_parser.add_argument(
        "--cwd",
        default=str(Path.cwd()),
        help="Workspace directory for Codex. Defaults to the current directory.",
    )
    resume_parser.add_argument("--name", required=True, help="Managed lane name.")
    resume_parser.add_argument("--prompt", required=True, help="Prompt sent after resume.")
    resume_target = resume_parser.add_mutually_exclusive_group(required=True)
    resume_target.add_argument("--session-id", help="Codex session id or thread name.")
    resume_target.add_argument(
        "--last",
        action="store_true",
        help="Resume the most recent Codex session.",
    )
    resume_parser.add_argument(
        "--codex-bin",
        default="codex",
        help="Codex executable name or path.",
    )
    resume_parser.add_argument(
        "--codex-model",
        help="Pass -m/--model to the resumed Codex worker.",
    )
    resume_parser.add_argument(
        "--codex-config",
        action="append",
        default=[],
        help="Pass one -c key=value override to the resumed Codex worker. Repeatable.",
    )
    resume_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    adopt_parser = subparsers.add_parser(
        "adopt", help="Register an existing tmux session as a managed Codex lane."
    )
    _add_state_root_arg(adopt_parser)
    adopt_parser.add_argument("--cwd", required=True, help="Workspace directory.")
    adopt_parser.add_argument("--name", required=True, help="Managed lane name.")
    adopt_parser.add_argument("--tmux-session", required=True, help="Existing tmux session.")
    adopt_parser.add_argument(
        "--prompt",
        default="接管已有 tmux 会话",
        help="Short note stored in the managed registry.",
    )
    adopt_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    discover_parser = subparsers.add_parser(
        "discover", help="List existing tmux sessions that can be adopted."
    )
    _add_state_root_arg(discover_parser)
    discover_parser.add_argument(
        "--cwd",
        default=str(Path.cwd()),
        help="Workspace directory used in generated adopt commands.",
    )
    discover_parser.add_argument(
        "--adopt-index",
        type=int,
        help="Adopt the 1-based candidate index from the discovery result.",
    )
    discover_parser.add_argument(
        "--adopt-first",
        action="store_true",
        help="Adopt the first discovered Codex-like tmux session.",
    )
    discover_parser.add_argument(
        "--name",
        help="Managed lane name when adopting. Defaults to the suggested candidate name.",
    )
    discover_parser.add_argument(
        "--prompt",
        default="接管已有 tmux 会话",
        help="Short note stored in the managed registry when adopting.",
    )
    discover_parser.add_argument(
        "--include-all",
        action="store_true",
        help="Include tmux sessions whose pane text does not look like Codex.",
    )
    discover_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    archive_parser = subparsers.add_parser(
        "archive", help="Archive a managed Codex lane so it stops appearing as active."
    )
    _add_state_root_arg(archive_parser)
    archive_parser.add_argument("--name", required=True, help="Managed lane name.")
    archive_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    send_parser = subparsers.add_parser(
        "send", help="Send one line to a tmux-managed Codex process."
    )
    _add_state_root_arg(send_parser)
    send_parser.add_argument("--name", required=True, help="Managed lane name.")
    send_parser.add_argument("--text", required=True, help="Text to send.")
    send_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    repair_parser = subparsers.add_parser(
        "repair-hooks",
        help="Repair tmux bell hooks for registered managed Codex lanes.",
    )
    _add_state_root_arg(repair_parser)
    repair_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    start_here_parser = subparsers.add_parser(
        "start-here",
        help="Print the shortest human-first Supervisor trial workflow.",
    )
    _add_state_root_arg(start_here_parser)
    start_here_parser.add_argument(
        "--cwd",
        default=str(Path.cwd()),
        help="Workspace directory. Defaults to the current directory.",
    )
    start_here_parser.add_argument(
        "--goal",
        default="让 Supervisor 根据当前项目文档继续推进下一步可验证任务。",
        help="The first goal to hand to Supervisor.",
    )
    start_here_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Web dashboard host used in the printed command.",
    )
    start_here_parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Web dashboard port used in the printed command.",
    )
    start_here_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    guide_parser = subparsers.add_parser(
        "guide", help="Print a ready-to-run Supervisor workflow."
    )
    guide_parser.add_argument(
        "--cwd",
        default=str(Path.cwd()),
        help="Workspace directory. Defaults to the current directory.",
    )
    guide_parser.add_argument(
        "--name",
        default="lane-a",
        help="Managed lane name used in generated commands.",
    )
    guide_parser.add_argument(
        "--tmux-session",
        help="tmux session name. Defaults to --name.",
    )
    guide_parser.add_argument(
        "--prompt",
        default="继续推进当前任务，并在完成或阻塞时按 SUPERVISOR_STATUS/SUMMARY/NEXT 汇报。",
        help="Prompt used by the launch command.",
    )
    guide_parser.add_argument(
        "--interval",
        type=int,
        default=30,
        help="Supervise loop interval seconds.",
    )
    guide_parser.add_argument(
        "--worker-profile",
        choices=api.WORKER_PROFILE_CHOICES,
        default=api.DEFAULT_WORKER_PROFILE,
        help="Worker profile used in generated loop/daemon commands.",
    )
    guide_parser.add_argument(
        "--worker-codex-model",
        help="Codex worker model used in generated loop/daemon commands.",
    )
    guide_parser.add_argument(
        "--worker-codex-config",
        action="append",
        help=(
            "Codex worker -c key=value override used in generated loop/daemon "
            "commands. Repeatable; replaces the guide default when provided."
        ),
    )
    guide_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    return parser
