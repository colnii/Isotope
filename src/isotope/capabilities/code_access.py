"""Controlled code read and search capabilities for native coding."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping

from ..platform.schemas.input_contract import missing_required_input_keys


CODE_READ_CAPABILITY = "code.read"
CODE_SEARCH_CAPABILITY = "code.search"
CODE_CAPABILITIES = frozenset({CODE_READ_CAPABILITY, CODE_SEARCH_CAPABILITY})

_DEFAULT_MAX_EXCERPT_CHARS = 2000
_MAX_EXCERPT_CHARS = 8000
_DEFAULT_MAX_RESULTS = 20
_MAX_RESULTS = 100
_SKIPPED_DIRS = frozenset(
    {".git", ".hg", ".mypy_cache", ".pytest_cache", ".venv", "__pycache__"}
)
_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:")


def is_code_access_capability(capability_id: str) -> bool:
    return capability_id in CODE_CAPABILITIES


def validate_code_access_inputs(
    *,
    capability_id: str,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    if capability_id == CODE_READ_CAPABILITY:
        return _validate_code_read_inputs(inputs=inputs, missing_inputs=missing_inputs)
    if capability_id == CODE_SEARCH_CAPABILITY:
        return _validate_code_search_inputs(inputs=inputs, missing_inputs=missing_inputs)
    return dict(inputs or {})


def run_code_read(*, inputs: Mapping[str, Any] | None) -> dict[str, Any]:
    required_inputs = ["root", "cwd", "path"]
    missing_inputs = _missing_inputs(required_inputs, inputs)
    if missing_inputs:
        raise ValueError("missing required capability inputs: " + ", ".join(missing_inputs))
    input_mapping = _validate_code_read_inputs(
        inputs=inputs,
        missing_inputs=missing_inputs,
    )
    cwd = Path(input_mapping["cwd"]).expanduser()
    path = input_mapping["path"]
    target = _workspace_path(cwd, path, field_name="path")
    read_result = _read_text_excerpt(
        target,
        path=path,
        max_excerpt_chars=input_mapping["max_excerpt_chars"],
    )
    return {
        "kind": "capability_run_result",
        "capability_id": CODE_READ_CAPABILITY,
        "status": "completed",
        "runner_kind": "deterministic_readonly",
        "code_read": read_result,
    }


def run_code_search(*, inputs: Mapping[str, Any] | None) -> dict[str, Any]:
    required_inputs = ["root", "cwd", "query"]
    missing_inputs = _missing_inputs(required_inputs, inputs)
    if missing_inputs:
        raise ValueError("missing required capability inputs: " + ", ".join(missing_inputs))
    input_mapping = _validate_code_search_inputs(
        inputs=inputs,
        missing_inputs=missing_inputs,
    )
    cwd = Path(input_mapping["cwd"]).expanduser()
    query = input_mapping["query"]
    max_results = input_mapping["max_results"]
    max_excerpt_chars = input_mapping["max_excerpt_chars"]
    matches: list[dict[str, Any]] = []
    visited_match_count = 0

    if not cwd.exists():
        status = "cwd_missing"
    elif not cwd.is_dir():
        status = "cwd_not_directory"
    else:
        status = "matched"
        for base_path in input_mapping["include_paths"]:
            search_root = _workspace_path(cwd, base_path, field_name="include_paths")
            for file_path in _iter_text_candidate_files(search_root):
                relative_path = _relative_workspace_path(cwd, file_path)
                file_matches = _search_file(
                    file_path,
                    relative_path=relative_path,
                    query=query,
                    max_excerpt_chars=max_excerpt_chars,
                )
                for match in file_matches:
                    visited_match_count += 1
                    if len(matches) < max_results:
                        matches.append(match)
        if not matches and visited_match_count == 0:
            status = "no_matches"

    return {
        "kind": "capability_run_result",
        "capability_id": CODE_SEARCH_CAPABILITY,
        "status": "completed",
        "runner_kind": "deterministic_readonly",
        "code_search": {
            "status": status,
            "query": query,
            "include_paths": list(input_mapping["include_paths"]),
            "match_count": len(matches),
            "total_match_count": visited_match_count,
            "truncated": visited_match_count > len(matches),
            "matches": matches,
            "content_policy": "bounded_excerpts_only",
        },
    }


def _missing_inputs(
    required_inputs: list[str], inputs: Mapping[str, Any] | None
) -> list[str]:
    return missing_required_input_keys(inputs, required_inputs)


def _validate_code_read_inputs(
    *,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    input_mapping = dict(inputs or {})
    _validate_non_empty_strings(input_mapping, ("root", "cwd", "path"), missing_inputs)
    if "path" not in missing_inputs:
        input_mapping["path"] = _safe_relative_path(input_mapping["path"], field_name="path")
    input_mapping["max_excerpt_chars"] = _bounded_int(
        input_mapping.get("max_excerpt_chars", _DEFAULT_MAX_EXCERPT_CHARS),
        field_name="max_excerpt_chars",
        minimum=1,
        maximum=_MAX_EXCERPT_CHARS,
    )
    return input_mapping


def _validate_code_search_inputs(
    *,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    input_mapping = dict(inputs or {})
    _validate_non_empty_strings(input_mapping, ("root", "cwd", "query"), missing_inputs)
    include_paths = input_mapping.get("include_paths", ["."])
    if include_paths is None:
        include_paths = ["."]
    if not isinstance(include_paths, list):
        raise ValueError("include_paths must be a list of relative paths")
    input_mapping["include_paths"] = [
        _safe_relative_path(path, field_name="include_paths", allow_dot=True)
        for path in include_paths
    ]
    input_mapping["max_results"] = _bounded_int(
        input_mapping.get("max_results", _DEFAULT_MAX_RESULTS),
        field_name="max_results",
        minimum=1,
        maximum=_MAX_RESULTS,
    )
    input_mapping["max_excerpt_chars"] = _bounded_int(
        input_mapping.get("max_excerpt_chars", _DEFAULT_MAX_EXCERPT_CHARS),
        field_name="max_excerpt_chars",
        minimum=1,
        maximum=_MAX_EXCERPT_CHARS,
    )
    return input_mapping


def _validate_non_empty_strings(
    input_mapping: dict[str, Any],
    names: tuple[str, ...],
    missing_inputs: list[str],
) -> None:
    for name in names:
        if name in missing_inputs:
            continue
        value = input_mapping.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
        input_mapping[name] = value.strip()


def _safe_relative_path(value: Any, *, field_name: str, allow_dot: bool = False) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty relative path")
    candidate = value.strip().replace("\\", "/")
    path = PurePosixPath(candidate)
    if (
        path.is_absolute()
        or _WINDOWS_DRIVE_RE.match(candidate)
        or ".." in path.parts
    ):
        raise ValueError(f"{field_name} must stay inside the workspace")
    if candidate == ".":
        if allow_dot:
            return "."
        raise ValueError(f"{field_name} must name a workspace-relative path")
    if candidate == "":
        raise ValueError(f"{field_name} must name a workspace-relative path")
    return candidate


def _bounded_int(value: Any, *, field_name: str, minimum: int, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    if value < minimum or value > maximum:
        raise ValueError(f"{field_name} must be between {minimum} and {maximum}")
    return value


def _workspace_path(cwd: Path, relative_path: str, *, field_name: str) -> Path:
    cwd_resolved = cwd.resolve(strict=False)
    candidate = (cwd / relative_path).resolve(strict=False)
    if not candidate.is_relative_to(cwd_resolved):
        raise ValueError(f"{field_name} must stay inside the workspace")
    return candidate


def _relative_workspace_path(cwd: Path, path: Path) -> str:
    return path.resolve(strict=False).relative_to(cwd.resolve(strict=False)).as_posix()


def _read_text_excerpt(
    target: Path,
    *,
    path: str,
    max_excerpt_chars: int,
) -> dict[str, Any]:
    if not target.exists():
        return _code_read_status("missing", path=path)
    if not target.is_file():
        return _code_read_status("not_file", path=path)
    raw = target.read_bytes()
    digest = sha256(raw).hexdigest()
    if b"\x00" in raw:
        return _code_read_status(
            "unsupported_binary",
            path=path,
            byte_count=len(raw),
            sha256_hex=digest,
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return _code_read_status(
            "unsupported_encoding",
            path=path,
            byte_count=len(raw),
            sha256_hex=digest,
        )
    excerpt = text[:max_excerpt_chars]
    return {
        "status": "readable",
        "path": path,
        "byte_count": len(raw),
        "line_count": len(text.splitlines()),
        "excerpt": excerpt,
        "truncated": len(text) > len(excerpt),
        "code_ref": {
            "ref_type": "code",
            "scope": "workspace",
            "path": path,
            "sha256": digest,
        },
        "content_policy": "bounded_excerpts_only",
    }


def _code_read_status(
    status: str,
    *,
    path: str,
    byte_count: int | None = None,
    sha256_hex: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": status,
        "path": path,
        "excerpt": "",
        "truncated": False,
        "content_policy": "bounded_excerpts_only",
    }
    if byte_count is not None:
        payload["byte_count"] = byte_count
    if sha256_hex is not None:
        payload["code_ref"] = {
            "ref_type": "code",
            "scope": "workspace",
            "path": path,
            "sha256": sha256_hex,
        }
    return payload


def _iter_text_candidate_files(root: Path):
    if root.is_file():
        yield root
        return
    if not root.exists() or not root.is_dir():
        return
    for child in sorted(root.iterdir(), key=lambda candidate: candidate.name):
        if child.is_dir():
            if child.name not in _SKIPPED_DIRS:
                yield from _iter_text_candidate_files(child)
        elif child.is_file():
            yield child


def _search_file(
    file_path: Path,
    *,
    relative_path: str,
    query: str,
    max_excerpt_chars: int,
) -> list[dict[str, Any]]:
    raw = file_path.read_bytes()
    if b"\x00" in raw:
        return []
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return []
    matches: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if query not in line:
            continue
        excerpt = line[:max_excerpt_chars]
        matches.append(
            {
                "path": relative_path,
                "line_number": line_number,
                "excerpt": excerpt,
                "truncated": len(line) > len(excerpt),
                "code_ref": {
                    "ref_type": "code",
                    "scope": "workspace",
                    "path": relative_path,
                    "line_number": line_number,
                },
            }
        )
    return matches


__all__ = [
    "CODE_CAPABILITIES",
    "CODE_READ_CAPABILITY",
    "CODE_SEARCH_CAPABILITY",
    "is_code_access_capability",
    "run_code_read",
    "run_code_search",
    "validate_code_access_inputs",
]
