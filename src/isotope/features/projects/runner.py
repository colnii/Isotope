"""CLI runner for the project feature flow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .flow import ProjectFlow


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Isotope project feature flow.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create", help="Create one project summary.")
    create_parser.add_argument("--root", required=True, help="Runtime root directory.")
    create_parser.add_argument("--name", required=True, help="Project name.")
    create_parser.add_argument("--summary", required=True, help="Project summary.")
    create_parser.add_argument("--json", action="store_true", help="Print JSON output.")

    get_parser = subparsers.add_parser("get", help="Read one project summary.")
    get_parser.add_argument("--root", required=True, help="Runtime root directory.")
    get_parser.add_argument("--project-id", help="Project id.")
    get_parser.add_argument("--json", action="store_true", help="Print JSON output.")

    detail_parser = subparsers.add_parser(
        "detail",
        help="Read one project with linked task and file summaries.",
    )
    detail_parser.add_argument("--root", required=True, help="Runtime root directory.")
    detail_parser.add_argument("--project-id", help="Project id.")
    detail_parser.add_argument("--json", action="store_true", help="Print JSON output.")

    list_parser = subparsers.add_parser("list", help="List project summaries.")
    list_parser.add_argument("--root", required=True, help="Runtime root directory.")
    list_parser.add_argument("--json", action="store_true", help="Print JSON output.")

    task_parser = subparsers.add_parser("add-task", help="Link a task id to a project.")
    task_parser.add_argument("--root", required=True, help="Runtime root directory.")
    task_parser.add_argument("--project-id", help="Project id.")
    task_parser.add_argument("--task-id", help="Task id.")
    task_parser.add_argument("--json", action="store_true", help="Print JSON output.")

    file_parser = subparsers.add_parser("add-file", help="Link a file id to a project.")
    file_parser.add_argument("--root", required=True, help="Runtime root directory.")
    file_parser.add_argument("--project-id", help="Project id.")
    file_parser.add_argument("--file-id", help="File id.")
    file_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        flow = ProjectFlow.in_process(Path(args.root))
        if args.command == "create":
            summary = flow.create_project(name=args.name, summary=args.summary)
            return _emit_project(args, summary.to_dict())
        if args.command == "get":
            if not args.project_id:
                raise ValueError("get requires --project-id")
            summary = flow.get_project(args.project_id)
            return _emit_project(args, summary.to_dict())
        if args.command == "detail":
            if not args.project_id:
                raise ValueError("detail requires --project-id")
            detail = flow.get_project_detail(args.project_id)
            return _emit_project_detail(args, detail.to_dict())
        if args.command == "list":
            summaries = [summary.to_dict() for summary in flow.list_projects()]
            if args.json:
                _print_json({"status": "ok", "projects": summaries})
            else:
                for summary in flow.list_projects():
                    print(f"{summary.project_id}: {summary.name}")
            return 0
        if args.command == "add-task":
            if not args.project_id:
                raise ValueError("add-task requires --project-id")
            if not args.task_id:
                raise ValueError("add-task requires --task-id")
            summary = flow.add_task(args.project_id, args.task_id)
            return _emit_project(args, summary.to_dict())
        if args.command == "add-file":
            if not args.project_id:
                raise ValueError("add-file requires --project-id")
            if not args.file_id:
                raise ValueError("add-file requires --file-id")
            summary = flow.add_file(args.project_id, args.file_id)
            return _emit_project(args, summary.to_dict())
    except ValueError as exc:
        if getattr(args, "json", False):
            _print_json(
                {
                    "status": "error",
                    "error": {
                        "code": "project_runner_error",
                        "message": str(exc),
                    },
                }
            )
        else:
            print(f"error: {exc}")
        return 2
    parser.error(f"unknown command: {args.command}")
    return 2


def _emit_project(args: argparse.Namespace, project: dict[str, Any]) -> int:
    if args.json:
        _print_json({"status": "ok", "project": project})
    else:
        print(f"{project['project_id']}: {project['name']}")
    return 0


def _emit_project_detail(args: argparse.Namespace, detail: dict[str, Any]) -> int:
    if args.json:
        _print_json({"status": "ok", "project_detail": detail})
    else:
        project = detail["project"]
        print(
            f"{project['project_id']}: {project['name']} "
            f"({len(detail['tasks'])} tasks, {len(detail['files'])} files)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
