"""CLI runner for the web research feature."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
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
    list_parser = subparsers.add_parser("list", help="List stored research artifacts.")
    list_parser.add_argument("--root", required=True, help="Runtime root directory.")
    list_parser.add_argument(
        "--artifact-type",
        help="Filter by exact research artifact type, such as research.provider_trace.",
    )
    list_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of research artifacts to list.",
    )
    list_parser.add_argument("--json", action="store_true", help="Print JSON output.")
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
                print_research_inspect_plain(payload)
            return 0
        if args.command == "list":
            payload = list_research_artifacts(
                Path(args.root),
                artifact_type=args.artifact_type,
                limit=args.limit,
            )
            if args.json:
                _print_json(payload)
            else:
                print_research_list_plain(payload)
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
        _print_provider_attempt_summary(error)
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


def list_research_artifacts(
    root: Path,
    *,
    artifact_type: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    if limit < 1:
        raise ValueError("research list requires --limit >= 1")
    if artifact_type is not None and not artifact_type.startswith("research."):
        raise ValueError("--artifact-type must start with research.")
    store = ArtifactStore(root)
    records: list[dict[str, Any]] = []
    runs_dir = root / "runs"
    if not runs_dir.exists():
        return {"status": "ok", "count": 0, "artifacts": []}
    for run_dir in sorted(runs_dir.iterdir()):
        if not run_dir.is_dir():
            continue
        for artifact in store.list_artifacts(run_dir.name):
            if not artifact.artifact_type.startswith("research."):
                continue
            if artifact_type is not None and artifact.artifact_type != artifact_type:
                continue
            path = store.artifact_path(artifact.run_id, artifact.artifact_id)
            modified_at = _modified_at(path)
            records.append(
                {
                    "run_id": artifact.run_id,
                    "artifact_id": artifact.artifact_id,
                    "artifact_type": artifact.artifact_type,
                    "summary": artifact.summary,
                    "ref": artifact.ref.to_dict(),
                    "modified_at": modified_at,
                }
            )
    records.sort(
        key=lambda record: (
            str(record["modified_at"]),
            str(record["run_id"]),
            str(record["artifact_id"]),
        ),
        reverse=True,
    )
    limited = records[:limit]
    return {"status": "ok", "count": len(limited), "artifacts": limited}


def _modified_at(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _decode_json_content(content: str) -> Any:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return content


def print_research_inspect_plain(payload: dict[str, Any]) -> None:
    artifact = payload["artifact"]
    ref = artifact["ref"]
    print(f"status: {payload['status']}")
    print(f"artifact: {artifact['artifact_type']} {ref['artifact_id']}")
    print(f"run: {ref['run_id']}")
    print(f"summary: {artifact['summary']}")
    content = payload["content"]
    if isinstance(content, (dict, list)):
        if artifact["artifact_type"] == "research.provider_trace" and isinstance(content, dict):
            _print_provider_trace_summary(content)
        print(json.dumps(content, ensure_ascii=False, sort_keys=True))
    else:
        print(str(content))


def print_research_list_plain(payload: dict[str, Any]) -> None:
    print(f"status: {payload['status']}")
    print(f"artifacts: {payload['count']}")
    for artifact in payload.get("artifacts", []):
        print(
            "artifact: "
            f"{artifact.get('artifact_type', '')} "
            f"{artifact.get('artifact_id', '')} "
            f"run: {artifact.get('run_id', '')} "
            f"{artifact.get('summary', '')}"
        )


def _print_provider_trace_summary(content: dict[str, Any]) -> None:
    error = content.get("error")
    if not isinstance(error, dict):
        return
    print(f"provider: {content.get('provider', '')}")
    print(f"query: {content.get('query', '')}")
    print(f"retryable: {str(error.get('retryable', False)).lower()}")
    print(f"error: {error.get('message', '')}")
    _print_provider_attempt_summary(error)


def _print_provider_attempt_summary(error: dict[str, Any]) -> None:
    details = error.get("details")
    if not isinstance(details, dict):
        return
    attempts = details.get("attempts")
    if not isinstance(attempts, list) or not attempts:
        return
    attempt_count = details.get("attempt_count")
    if not isinstance(attempt_count, int):
        attempt_count = len(attempts)
    retry_exhausted = str(details.get("retry_exhausted", False)).lower()
    print(f"attempts: {attempt_count} retry_exhausted: {retry_exhausted}")
    for attempt in attempts:
        if not isinstance(attempt, dict):
            continue
        print(
            "- attempt "
            f"{attempt.get('attempt', '')} "
            f"retryable: {str(attempt.get('retryable', False)).lower()} "
            f"{_attempt_message(attempt)}"
        )


def _attempt_message(attempt: dict[str, Any]) -> str:
    details = attempt.get("details")
    if isinstance(details, dict):
        messages = details.get("codex_error_messages")
        if isinstance(messages, list):
            readable_messages = [message for message in messages if isinstance(message, str) and message]
            if readable_messages:
                return "; ".join(readable_messages)
    message = attempt.get("message")
    return message if isinstance(message, str) else ""


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
