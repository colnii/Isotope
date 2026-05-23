"""Argument parser construction for the LLM live-smoke CLI."""

from __future__ import annotations

import argparse


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Isotope LLM developer smoke checks.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    terminal_tool = subparsers.add_parser(
        "terminal-tool",
        help="Run a provider smoke that exposes only terminal_exec.",
    )
    terminal_tool.add_argument("--json", action="store_true", help="Print JSON output.")
    terminal_tool.add_argument(
        "--fake-provider",
        action="store_true",
        help="Use a deterministic fake provider instead of configured ISOTOPE_LLM_* provider settings.",
    )
    terminal_tool.add_argument(
        "--diagnose",
        action="store_true",
        help="Include a low-sensitive readiness diagnosis in the smoke result.",
    )
    terminal_tool.add_argument(
        "--root",
        help="Optional smoke root. Defaults to a temporary directory.",
    )
    terminal_tool.add_argument(
        "--max-tokens",
        type=int,
        default=128,
        help="Max tokens passed to the provider.",
    )
    product_chat = subparsers.add_parser(
        "product-chat",
        help="Run the product-chat provider smoke with a fake Codex runner.",
    )
    product_chat.add_argument("--json", action="store_true", help="Print JSON output.")
    product_chat.add_argument(
        "--fake-provider",
        action="store_true",
        help="Use a deterministic fake provider instead of configured ISOTOPE_LLM_* provider settings.",
    )
    product_chat.add_argument(
        "--diagnose",
        action="store_true",
        help="Include a low-sensitive readiness diagnosis in the smoke result.",
    )
    product_chat.add_argument(
        "--root",
        help="Optional smoke root. Defaults to a temporary directory.",
    )
    product_chat.add_argument(
        "--max-tokens",
        type=int,
        default=128,
        help="Max tokens passed to the provider.",
    )
    product_chat.add_argument(
        "--codex-executable",
        default="codex",
        help="Codex executable name recorded in the fake-runner app config.",
    )
    product_chat.add_argument(
        "--timeout-seconds",
        type=int,
        default=17,
        help="Codex task timeout recorded in the fake-runner app config.",
    )
    product_chat.add_argument(
        "--max-output-bytes",
        type=int,
        default=4096,
        help="Codex task output cap recorded in the fake-runner app config.",
    )
    product_chat_entry = subparsers.add_parser(
        "product-chat-entry",
        help="Run product-chat preflight, then submit one user message if ready.",
    )
    product_chat_entry.add_argument("--json", action="store_true", help="Print JSON output.")
    product_chat_entry.add_argument(
        "--fake-provider",
        action="store_true",
        help="Use a deterministic fake provider instead of configured ISOTOPE_LLM_* provider settings.",
    )
    product_chat_entry.add_argument(
        "--fake-entry-pending",
        action="store_true",
        help="With --fake-provider, make the entry turn select codex_task and save a resumable pending state.",
    )
    product_chat_entry.add_argument(
        "--message",
        required=False,
        help="One user message to submit after product-chat preflight passes.",
    )
    product_chat_entry.add_argument(
        "--state-file",
        help="Optional local JSON file for resuming a pending product-chat entry approval.",
    )
    product_chat_entry.add_argument(
        "--resume-state",
        help="Resume a pending product-chat entry from a local JSON state file.",
    )
    product_chat_entry.add_argument(
        "--root",
        help="Optional command root. Defaults to a temporary directory.",
    )
    product_chat_entry.add_argument(
        "--max-tokens",
        type=int,
        default=128,
        help="Max tokens passed to the provider.",
    )
    product_chat_entry.add_argument(
        "--codex-executable",
        default="codex",
        help="Codex executable name recorded in the fake-runner app config.",
    )
    product_chat_entry.add_argument(
        "--timeout-seconds",
        type=int,
        default=17,
        help="Codex task timeout recorded in the fake-runner app config.",
    )
    product_chat_entry.add_argument(
        "--max-output-bytes",
        type=int,
        default=4096,
        help="Codex task output cap recorded in the fake-runner app config.",
    )
    return parser
