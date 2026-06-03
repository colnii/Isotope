"""Controlled code edit capabilities for native coding."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping

from ..platform.schemas.input_contract import missing_required_input_keys


CODE_APPLY_PATCH_CAPABILITY = "code.apply_patch"

_HUNK_RE = re.compile(
    r"^@@ -(?P<old_start>\d+)(?:,(?P<old_count>\d+))? "
    r"\+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? @@"
)
_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:")


@dataclass(frozen=True)
class PatchHunk:
    old_start: int
    lines: tuple[str, ...]


@dataclass(frozen=True)
class PatchFile:
    path: str
    hunks: tuple[PatchHunk, ...]


def is_code_edit_capability(capability_id: str) -> bool:
    return capability_id == CODE_APPLY_PATCH_CAPABILITY


def validate_code_edit_inputs(
    *,
    capability_id: str,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    if capability_id != CODE_APPLY_PATCH_CAPABILITY:
        return dict(inputs or {})
    input_mapping = dict(inputs or {})
    for name in ("root", "cwd", "patch"):
        if name in missing_inputs:
            continue
        value = input_mapping.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
        input_mapping[name] = value if name == "patch" else value.strip()
    return input_mapping


def run_code_apply_patch(*, inputs: Mapping[str, Any] | None) -> dict[str, Any]:
    required_inputs = ["root", "cwd", "patch"]
    missing_inputs = _missing_inputs(required_inputs, inputs)
    if missing_inputs:
        raise ValueError("missing required capability inputs: " + ", ".join(missing_inputs))
    input_mapping = validate_code_edit_inputs(
        capability_id=CODE_APPLY_PATCH_CAPABILITY,
        inputs=inputs,
        missing_inputs=missing_inputs,
    )
    cwd = Path(input_mapping["cwd"]).expanduser()
    if not cwd.exists():
        raise ValueError("cwd must exist before applying patch")
    if not cwd.is_dir():
        raise ValueError("cwd must be a directory before applying patch")

    patch_files = _parse_unified_patch(input_mapping["patch"])
    pending_writes: list[tuple[Path, bytes]] = []
    changed_files: list[str] = []
    for patch_file in patch_files:
        target = _workspace_path(cwd, patch_file.path)
        original = _read_original_lines(target)
        new_lines = _apply_patch_file(original, patch_file)
        pending_writes.append((target, "".join(new_lines).encode("utf-8")))
        changed_files.append(patch_file.path)

    for target, content in pending_writes:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    changed_files = sorted(dict.fromkeys(changed_files))
    return {
        "kind": "capability_run_result",
        "capability_id": CODE_APPLY_PATCH_CAPABILITY,
        "status": "completed",
        "runner_kind": "deterministic_local",
        "patch_result": {
            "status": "applied",
            "changed_files": changed_files,
            "file_count": len(changed_files),
            "hunk_count": sum(len(patch_file.hunks) for patch_file in patch_files),
            "write_policy": "workspace_relative_patch_only",
            "content_policy": "diff_summary_only",
        },
    }


def _missing_inputs(
    required_inputs: list[str], inputs: Mapping[str, Any] | None
) -> list[str]:
    return missing_required_input_keys(inputs, required_inputs)


def _parse_unified_patch(patch_text: str) -> list[PatchFile]:
    lines = patch_text.splitlines(keepends=True)
    patch_files: list[PatchFile] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.startswith("--- "):
            index += 1
            continue
        if index + 1 >= len(lines) or not lines[index + 1].startswith("+++ "):
            raise ValueError("patch must use unified diff file headers")
        old_path = _header_path(lines[index])
        new_path = _header_path(lines[index + 1])
        path = _patch_target_path(old_path, new_path)
        index += 2
        hunks: list[PatchHunk] = []
        while index < len(lines) and not lines[index].startswith("--- "):
            hunk_match = _HUNK_RE.match(lines[index])
            if hunk_match is None:
                raise ValueError("patch must use unified diff hunks")
            old_start = int(hunk_match.group("old_start"))
            index += 1
            hunk_lines: list[str] = []
            while (
                index < len(lines)
                and not lines[index].startswith("@@ ")
                and not lines[index].startswith("--- ")
            ):
                hunk_lines.append(lines[index])
                index += 1
            hunks.append(PatchHunk(old_start=old_start, lines=tuple(hunk_lines)))
        if not hunks:
            raise ValueError("patch file must include at least one hunk")
        patch_files.append(PatchFile(path=path, hunks=tuple(hunks)))
    if not patch_files:
        raise ValueError("patch must include at least one file diff")
    return patch_files


def _header_path(line: str) -> str:
    parts = line.strip().split(maxsplit=1)
    if len(parts) != 2:
        raise ValueError("patch file header must include a path")
    return parts[1].split("\t", maxsplit=1)[0]


def _patch_target_path(old_path: str, new_path: str) -> str:
    candidate = new_path if new_path != "/dev/null" else old_path
    if candidate in {"/dev/null", ""}:
        raise ValueError("patch path must name a workspace-relative file")
    if candidate.startswith(("a/", "b/")):
        candidate = candidate[2:]
    return _safe_patch_path(candidate)


def _safe_patch_path(value: str) -> str:
    candidate = value.strip().replace("\\", "/")
    path = PurePosixPath(candidate)
    if (
        not candidate
        or candidate == "."
        or path.is_absolute()
        or _WINDOWS_DRIVE_RE.match(candidate)
        or ".." in path.parts
    ):
        raise ValueError("patch path must stay inside the workspace")
    return candidate


def _workspace_path(cwd: Path, relative_path: str) -> Path:
    cwd_resolved = cwd.resolve(strict=False)
    candidate = (cwd / relative_path).resolve(strict=False)
    if not candidate.is_relative_to(cwd_resolved):
        raise ValueError("patch path must stay inside the workspace")
    return candidate


def _read_original_lines(target: Path) -> list[str]:
    if not target.exists():
        return []
    if not target.is_file():
        raise ValueError("patch target must be a file")
    try:
        return target.read_text(encoding="utf-8").splitlines(keepends=True)
    except UnicodeDecodeError as exc:
        raise ValueError("patch target must be utf-8 text") from exc


def _apply_patch_file(original: list[str], patch_file: PatchFile) -> list[str]:
    result: list[str] = []
    cursor = 0
    for hunk in patch_file.hunks:
        hunk_start = max(hunk.old_start - 1, 0)
        if hunk_start < cursor:
            raise ValueError("patch hunks must be ordered")
        result.extend(original[cursor:hunk_start])
        cursor = hunk_start
        for line in hunk.lines:
            if line.startswith("\\"):
                continue
            if not line:
                raise ValueError("patch hunk line must include an operation")
            operation = line[0]
            text = line[1:]
            if operation == " ":
                _require_context(original, cursor, text)
                result.append(text)
                cursor += 1
            elif operation == "-":
                _require_context(original, cursor, text)
                cursor += 1
            elif operation == "+":
                result.append(text)
            else:
                raise ValueError("patch hunk line must use unified diff operations")
    result.extend(original[cursor:])
    return result


def _require_context(original: list[str], cursor: int, expected: str) -> None:
    if cursor >= len(original) or original[cursor] != expected:
        raise ValueError("patch context mismatch")


__all__ = [
    "CODE_APPLY_PATCH_CAPABILITY",
    "is_code_edit_capability",
    "run_code_apply_patch",
    "validate_code_edit_inputs",
]
