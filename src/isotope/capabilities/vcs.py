"""Read-only VCS capabilities for native coding."""

from __future__ import annotations

from pathlib import Path
import subprocess
from typing import Any, Mapping

from ..platform.schemas.input_contract import missing_required_input_keys


VCS_STATUS_CAPABILITY = "vcs.status"
VCS_DIFF_CAPABILITY = "vcs.diff"
VCS_CAPABILITIES = frozenset({VCS_STATUS_CAPABILITY, VCS_DIFF_CAPABILITY})
_DEFAULT_MAX_STAT_CHARS = 4000


def is_vcs_capability(capability_id: str) -> bool:
    return capability_id in VCS_CAPABILITIES


def validate_vcs_inputs(
    *,
    capability_id: str,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    if capability_id not in VCS_CAPABILITIES:
        return dict(inputs or {})
    input_mapping = dict(inputs or {})
    for name in ("root", "cwd"):
        if name in missing_inputs:
            continue
        value = input_mapping.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
        input_mapping[name] = value.strip()
    input_mapping["max_stat_chars"] = _limited_int(
        input_mapping.get("max_stat_chars", _DEFAULT_MAX_STAT_CHARS),
        field_name="max_stat_chars",
        minimum=1,
        maximum=20000,
    )
    return input_mapping


def run_vcs_status(*, inputs: Mapping[str, Any] | None) -> dict[str, Any]:
    required_inputs = ["root", "cwd"]
    missing_inputs = _missing_inputs(required_inputs, inputs)
    if missing_inputs:
        raise ValueError("missing required capability inputs: " + ", ".join(missing_inputs))
    input_mapping = validate_vcs_inputs(
        capability_id=VCS_STATUS_CAPABILITY,
        inputs=inputs,
        missing_inputs=missing_inputs,
    )
    cwd = _git_workspace(input_mapping["cwd"])
    status_text = _git(cwd, ["status", "--porcelain=v1", "--branch"])
    parsed = _parse_status_porcelain(status_text)
    changed_files = parsed["changed_files"]
    return {
        "kind": "capability_run_result",
        "capability_id": VCS_STATUS_CAPABILITY,
        "status": "completed",
        "runner_kind": "deterministic_readonly",
        "vcs_status": {
            "status": "clean" if not changed_files else "dirty",
            "branch": parsed["branch"],
            "changed_file_count": len(changed_files),
            "changed_files": changed_files,
            "artifact_write": "not_performed",
            "command_policy": "fixed_git_subcommands_only",
        },
    }


def run_vcs_diff(*, inputs: Mapping[str, Any] | None) -> dict[str, Any]:
    required_inputs = ["root", "cwd"]
    missing_inputs = _missing_inputs(required_inputs, inputs)
    if missing_inputs:
        raise ValueError("missing required capability inputs: " + ", ".join(missing_inputs))
    input_mapping = validate_vcs_inputs(
        capability_id=VCS_DIFF_CAPABILITY,
        inputs=inputs,
        missing_inputs=missing_inputs,
    )
    cwd = _git_workspace(input_mapping["cwd"])
    changed_files = [
        path
        for path in _git(cwd, ["diff", "--name-only"]).splitlines()
        if path.strip()
    ]
    stat = _git(cwd, ["diff", "--stat"])
    stat_excerpt = stat[: input_mapping["max_stat_chars"]]
    return {
        "kind": "capability_run_result",
        "capability_id": VCS_DIFF_CAPABILITY,
        "status": "completed",
        "runner_kind": "deterministic_readonly",
        "vcs_diff": {
            "status": "clean" if not changed_files else "changed",
            "changed_file_count": len(changed_files),
            "changed_files": changed_files,
            "stat_excerpt": stat_excerpt,
            "stat_truncated": len(stat) > len(stat_excerpt),
            "artifact_write": "not_performed",
            "content_policy": "diff_summary_only",
            "command_policy": "fixed_git_subcommands_only",
        },
    }


def _missing_inputs(
    required_inputs: list[str], inputs: Mapping[str, Any] | None
) -> list[str]:
    return missing_required_input_keys(inputs, required_inputs)


def _git_workspace(cwd_value: str) -> Path:
    cwd = Path(cwd_value).expanduser()
    if not cwd.exists():
        raise ValueError("cwd must exist")
    if not cwd.is_dir():
        raise ValueError("cwd must be a directory")
    try:
        _git(cwd, ["rev-parse", "--is-inside-work-tree"])
    except ValueError as exc:
        raise ValueError("cwd must be inside a git repository") from exc
    return cwd


def _git(cwd: Path, args: list[str]) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "git command failed").strip()
        raise ValueError(message)
    return completed.stdout


def _parse_status_porcelain(text: str) -> dict[str, Any]:
    branch = None
    changed_files: list[dict[str, str]] = []
    for line in text.splitlines():
        if line.startswith("## "):
            branch = _branch_from_status_header(line[3:])
            continue
        if not line:
            continue
        if line.startswith("?? "):
            changed_files.append(
                {"path": line[3:], "index_status": "?", "worktree_status": "?"}
            )
            continue
        if len(line) < 4:
            continue
        changed_files.append(
            {
                "path": line[3:],
                "index_status": line[0],
                "worktree_status": line[1],
            }
        )
    return {
        "branch": branch,
        "changed_files": changed_files,
    }


def _branch_from_status_header(value: str) -> str | None:
    branch = value.split("...", maxsplit=1)[0].strip()
    if branch.startswith("No commits yet on "):
        return branch.removeprefix("No commits yet on ").strip()
    if branch == "HEAD (no branch)":
        return "HEAD"
    return branch or None


def _limited_int(value: Any, *, field_name: str, minimum: int, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    if value < minimum or value > maximum:
        raise ValueError(f"{field_name} must be between {minimum} and {maximum}")
    return value


__all__ = [
    "VCS_CAPABILITIES",
    "VCS_DIFF_CAPABILITY",
    "VCS_STATUS_CAPABILITY",
    "is_vcs_capability",
    "run_vcs_diff",
    "run_vcs_status",
    "validate_vcs_inputs",
]
