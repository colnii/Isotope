"""CLI runner for the web research feature."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ...platform.schemas.refs import make_artifact_ref
from ...workspace.artifacts import ArtifactStore
from .flow import ResearchFlow
from .providers import (
    CodexDelegatedResearchProvider,
    FakeResearchProvider,
    build_codex_cli_research_backend,
)


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Isotope research feature flow.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    search_parser = subparsers.add_parser("search", help="Run delegated research.")
    search_parser.add_argument("--root", required=True, help="Runtime root directory.")
    search_parser.add_argument("--query", help="Research query.")
    search_parser.add_argument(
        "--provider",
        default="fake",
        choices=("fake", "codex"),
        help="Research provider.",
    )
    search_parser.add_argument(
        "--workspace-root",
        help="Workspace root for Codex delegated research. Defaults to current directory.",
    )
    search_parser.add_argument(
        "--codex-executable",
        default="codex",
        help="Codex CLI executable for --provider codex.",
    )
    search_parser.add_argument("--codex-home", help="Codex home for --provider codex.")
    search_parser.add_argument("--model", help="Codex model for --provider codex.")
    search_parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=120,
        help="Codex delegated research timeout in seconds.",
    )
    search_parser.add_argument(
        "--max-attempts",
        type=int,
        default=2,
        help="Maximum Codex delegated provider attempts for retryable failures.",
    )
    search_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    inspect_parser = subparsers.add_parser("inspect", help="Inspect a research artifact.")
    inspect_parser.add_argument("--root", required=True, help="Runtime root directory.")
    inspect_parser.add_argument("--run-id", required=True, help="Run id for the artifact ref.")
    inspect_parser.add_argument("--artifact-id", required=True, help="Artifact id to inspect.")
    inspect_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "search":
            if not args.query:
                raise ValueError("research search requires --query")
            flow = ResearchFlow.in_process(
                Path(args.root),
                provider=_provider_from_args(args),
            )
            payload = flow.search(args.query).to_dict()
            if args.json:
                _print_json(payload)
            else:
                _print_plain(payload)
            return 0
        if args.command == "inspect":
            payload = inspect_research_artifact(
                Path(args.root),
                run_id=args.run_id,
                artifact_id=args.artifact_id,
            )
            if args.json:
                _print_json(payload)
            else:
                _print_inspect_plain(payload)
            return 0
    except (FileNotFoundError, ValueError) as exc:
        error = {
            "status": "error",
            "error": {"code": "research_runner_error", "message": str(exc)},
        }
        if getattr(args, "json", False):
            _print_json(error)
        else:
            print(f"error: {exc}")
        return 2
    parser.error(f"unknown command: {args.command}")
    return 2


def _print_plain(payload: dict[str, Any]) -> None:
    research = payload.get("research") or {}
    print(f"status: {payload['status']}")
    print(f"query: {research.get('query') or payload.get('query', '')}")
    print(f"evidence: {research.get('evidence_status', '')}")
    error = payload.get("error")
    if isinstance(error, dict):
        print(f"retryable: {str(error.get('retryable', False)).lower()}")
        print(f"error: {error.get('message', '')}")
    print_artifacts_plain(payload)
    for source in research.get("sources", []):
        print(f"- {source['title']} {source['url']}")


def inspect_research_artifact(root: Path, *, run_id: str, artifact_id: str) -> dict[str, Any]:
    ref = make_artifact_ref(run_id=run_id, artifact_id=artifact_id)
    store = ArtifactStore(root)
    metadata = store.get_metadata(ref, include_provenance=True)
    if not str(metadata["artifact_type"]).startswith("research."):
        raise ValueError("artifact is not a research artifact")
    content_text = store.get_content(ref)
    return {
        "status": "ok",
        "artifact": {
            **metadata,
            "ref": ref.to_dict(),
        },
        "content": _decode_json_content(content_text),
    }


def _decode_json_content(content: str) -> Any:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return content


def _print_inspect_plain(payload: dict[str, Any]) -> None:
    artifact = payload["artifact"]
    ref = artifact["ref"]
    print(f"status: {payload['status']}")
    print(f"artifact: {artifact['artifact_type']} {ref['artifact_id']}")
    print(f"run: {ref['run_id']}")
    print(f"summary: {artifact['summary']}")
    content = payload["content"]
    if isinstance(content, (dict, list)):
        print(json.dumps(content, ensure_ascii=False, sort_keys=True))
    else:
        print(str(content))


def print_artifacts_plain(payload: dict[str, Any]) -> None:
    for artifact in payload.get("artifacts", []):
        ref = artifact.get("ref") or {}
        print(
            "artifact: "
            f"{artifact.get('artifact_type', '')} "
            f"{ref.get('artifact_id', '')} "
            f"{artifact.get('summary', '')}"
        )


def _provider_from_args(args: argparse.Namespace):
    if args.provider == "fake":
        return FakeResearchProvider()
    if args.provider == "codex":
        return CodexDelegatedResearchProvider(
            build_codex_cli_research_backend(
                workspace_root=args.workspace_root or Path.cwd(),
                executable=args.codex_executable,
                codex_home=args.codex_home,
                model=args.model,
                timeout_seconds=args.timeout_seconds,
            ),
            max_attempts=args.max_attempts,
        )
    raise ValueError(f"unsupported research provider: {args.provider}")


if __name__ == "__main__":
    raise SystemExit(main())
