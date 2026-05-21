"""CLI runner for the workbench ask flow."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from ...llm.provider import LLMResponse, OpenAICompatibleChatProvider
from .flow import WorkbenchAskFlow
from .pool import resolve_workbench_ask_provider_from_env


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ask the Isotope workbench.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ask_parser = subparsers.add_parser("ask", help="Ask one question about the workbench.")
    ask_parser.add_argument("--root", required=True, help="Runtime root directory.")
    ask_parser.add_argument("--question", required=True, help="Question to answer.")
    ask_parser.add_argument("--limit", type=int, default=5, help="Search result limit.")
    ask_parser.add_argument("--max-tokens", type=int, default=512, help="Provider max tokens.")
    ask_parser.add_argument(
        "--mock-answer",
        help="Use a deterministic local answer instead of calling a real provider.",
    )
    ask_parser.add_argument(
        "--llm-pool",
        action="store_true",
        help="Use the local TOML LLM pool for the provider.",
    )
    ask_parser.add_argument(
        "--llm-pool-agent-name",
        help="Only use providers from this TOML agent group.",
    )
    ask_parser.add_argument("--provider-name", help="Provider label for OpenAI-compatible API.")
    ask_parser.add_argument("--base-url", help="OpenAI-compatible base URL.")
    ask_parser.add_argument("--model", help="Model name.")
    ask_parser.add_argument("--api-key", help="API key value.")
    ask_parser.add_argument("--api-key-env", help="Read API key from this environment variable.")
    ask_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "ask":
            provider = _provider_from_args(args)
            answer = WorkbenchAskFlow.in_process(Path(args.root), provider=provider).answer(
                args.question,
                search_limit=args.limit,
                max_tokens=args.max_tokens,
            )
            payload = {"status": "ok", "answer": answer.to_dict()}
            if args.json:
                _print_json(payload)
            else:
                counts = answer.workbench.counts
                print(f"answer: {answer.answer}")
                print(f"provider: {answer.provider}/{answer.model}")
                print(
                    "context: projects={projects} tasks={tasks} files={files} "
                    "search_results={search_results}".format(**counts)
                )
                if answer.references:
                    print(f"references: {_format_references(answer.references)}")
            return 0
    except ValueError as exc:
        if getattr(args, "json", False):
            _print_json(
                {
                    "status": "error",
                    "error": {
                        "code": "ask_runner_error",
                        "message": str(exc),
                    },
                }
            )
        else:
            print(f"error: {exc}")
        return 2
    parser.error(f"unknown command: {args.command}")
    return 2


def _provider_from_args(args: argparse.Namespace) -> Any:
    direct_provider_mode = any(
        value
        for value in (
            args.provider_name,
            args.base_url,
            args.model,
            args.api_key,
            args.api_key_env,
        )
    )
    provider_modes = [
        args.mock_answer is not None,
        args.llm_pool,
        direct_provider_mode,
    ]
    if sum(1 for mode in provider_modes if mode) > 1:
        raise ValueError(
            "only one provider mode is allowed: --mock-answer, --llm-pool, "
            "or direct provider config"
        )
    if args.mock_answer is not None:
        return _MockAskProvider(args.mock_answer)
    if args.llm_pool:
        return resolve_workbench_ask_provider_from_env(
            agent_name=args.llm_pool_agent_name,
        )
    missing = [
        name
        for name, value in (
            ("--provider-name", args.provider_name),
            ("--base-url", args.base_url),
            ("--model", args.model),
        )
        if not value
    ]
    api_key = _resolve_api_key(args)
    if api_key is None:
        missing.append("--api-key or --api-key-env")
    if missing:
        raise ValueError(
            "ask requires --mock-answer or provider config: " + ", ".join(missing)
        )
    return OpenAICompatibleChatProvider(
        provider=args.provider_name,
        api_key=api_key,
        base_url=args.base_url,
        model=args.model,
    )


def _format_references(references: tuple[Any, ...]) -> str:
    return "; ".join(
        _format_reference(reference)
        for reference in references
    )


def _format_reference(reference: Any) -> str:
    text = f"{reference.rank}. {reference.result_type} {reference.title}"
    return f"{text} - {reference.summary}" if reference.summary else text


def _resolve_api_key(args: argparse.Namespace) -> str | None:
    if args.api_key:
        return args.api_key
    if args.api_key_env:
        value = os.environ.get(args.api_key_env)
        if value and value.strip():
            return value.strip()
    return None


class _MockAskProvider:
    provider = "mock"
    model = "mock-workbench-ask"

    def __init__(self, answer: str) -> None:
        self.answer = answer

    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 512,
    ) -> LLMResponse:
        return LLMResponse(
            provider=self.provider,
            model=self.model,
            content=self.answer,
            finish_reason="stop",
            usage={"prompt_tokens": 0, "completion_tokens": 0},
            raw={"mock": True},
        )


if __name__ == "__main__":
    raise SystemExit(main())
