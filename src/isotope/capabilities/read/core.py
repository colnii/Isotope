"""Unified bounded read capability helpers."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping

from isotope.platform.schemas.input_contract import missing_required_input_keys

FILE_READ_CAPABILITY = "file.read"

_DEFAULT_MAX_EXCERPT_CHARS = 2000
_MAX_EXCERPT_CHARS = 8000
_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:")


def is_file_read_capability(capability_id: str) -> bool:
    return capability_id == FILE_READ_CAPABILITY


def validate_file_read_inputs(
    *,
    capability_id: str,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    if capability_id != FILE_READ_CAPABILITY:
        return dict(inputs or {})
    input_mapping = dict(inputs or {})
    _validate_non_empty_strings(input_mapping, ("scope", "path"), missing_inputs)
    scope = input_mapping.get("scope")
    if scope not in {"workspace", "local_file"}:
        raise ValueError("scope must be workspace or local_file")
    if scope == "workspace":
        _validate_non_empty_strings(input_mapping, ("cwd",), missing_inputs)
        if "path" not in missing_inputs:
            input_mapping["path"] = safe_workspace_relative_path(input_mapping["path"])
    if scope == "local_file":
        _validate_non_empty_strings(input_mapping, ("root",), [])
    input_mapping["max_excerpt_chars"] = limited_int(
        input_mapping.get("max_excerpt_chars", _DEFAULT_MAX_EXCERPT_CHARS),
        field_name="max_excerpt_chars",
        minimum=1,
        maximum=_MAX_EXCERPT_CHARS,
    )
    return input_mapping


def run_file_read(*, inputs: Mapping[str, Any] | None) -> dict[str, Any]:
    input_mapping = dict(inputs or {})
    if input_mapping.get("scope") == "local_file":
        root = input_mapping.get("root")
        if not isinstance(root, str) or not root.strip():
            raise ValueError("root must be a non-empty string")
    required_inputs = ["root", "scope", "path"]
    if input_mapping.get("scope") == "workspace":
        required_inputs.append("cwd")
    missing_inputs = missing_required_input_keys(input_mapping, required_inputs)
    if missing_inputs:
        raise ValueError("missing required capability inputs: " + ", ".join(missing_inputs))
    input_mapping = validate_file_read_inputs(
        capability_id=FILE_READ_CAPABILITY,
        inputs=input_mapping,
        missing_inputs=missing_inputs,
    )
    if input_mapping["scope"] == "workspace":
        cwd = Path(input_mapping["cwd"]).expanduser()
        path = input_mapping["path"]
        target = workspace_path(cwd, path, field_name="path")
        read_result = read_text_excerpt(
            target,
            path=path,
            scope="workspace",
            max_excerpt_chars=input_mapping["max_excerpt_chars"],
        )
        return {
            "kind": "capability_run_result",
            "capability_id": FILE_READ_CAPABILITY,
            "status": "completed",
            "runner_kind": "deterministic_projection",
            "read": read_result,
        }
    from .runtime import request_local_file_read_approval

    return request_local_file_read_approval(input_mapping)


def read_text_excerpt(
    target: Path,
    *,
    path: str,
    scope: str,
    max_excerpt_chars: int,
) -> dict[str, Any]:
    if not target.exists():
        return read_status("missing", path=path, scope=scope)
    if not target.is_file():
        return read_status("not_file", path=path, scope=scope)
    raw = target.read_bytes()
    digest = sha256(raw).hexdigest()
    if b"\x00" in raw:
        return read_status(
            "unsupported_binary",
            path=path,
            scope=scope,
            byte_count=len(raw),
            sha256_hex=digest,
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return read_status(
            "unsupported_encoding",
            path=path,
            scope=scope,
            byte_count=len(raw),
            sha256_hex=digest,
        )
    excerpt = text[:max_excerpt_chars]
    return {
        "scope": scope,
        "status": "readable",
        "path": path,
        "byte_count": len(raw),
        "line_count": len(text.splitlines()),
        "excerpt": excerpt,
        "truncated": len(text) > len(excerpt),
        "ref": {
            "ref_type": "file_read",
            "scope": scope,
            "path": path,
            "sha256": digest,
        },
        "content_policy": "limited_excerpts_only",
    }


def read_status(
    status: str,
    *,
    path: str,
    scope: str,
    byte_count: int | None = None,
    sha256_hex: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "scope": scope,
        "status": status,
        "path": path,
        "excerpt": "",
        "truncated": False,
        "content_policy": "limited_excerpts_only",
    }
    if byte_count is not None:
        result["byte_count"] = byte_count
    if sha256_hex is not None:
        result["ref"] = {
            "ref_type": "file_read",
            "scope": scope,
            "path": path,
            "sha256": sha256_hex,
        }
    return result


def safe_workspace_relative_path(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("path must be a non-empty relative path")
    candidate = value.strip().replace("\\", "/")
    path = PurePosixPath(candidate)
    if path.is_absolute() or _WINDOWS_DRIVE_RE.match(candidate) or ".." in path.parts:
        raise ValueError("path must stay inside the workspace")
    if candidate in {"", "."}:
        raise ValueError("path must name a workspace-relative path")
    return candidate


def workspace_path(cwd: Path, relative_path: str, *, field_name: str) -> Path:
    cwd_resolved = cwd.resolve(strict=False)
    candidate = (cwd / relative_path).resolve(strict=False)
    if not candidate.is_relative_to(cwd_resolved):
        raise ValueError(f"{field_name} must stay inside the workspace")
    return candidate


def limited_int(value: Any, *, field_name: str, minimum: int, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    if value < minimum or value > maximum:
        raise ValueError(f"{field_name} must be between {minimum} and {maximum}")
    return value


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
