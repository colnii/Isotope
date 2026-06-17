"""Tree-sitter universal syntax tree edit support."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping

from tree_sitter_language_pack import detect_language_from_path, get_parser

from ...platform.schemas.input_contract import missing_required_input_keys
from ..code_access import _safe_relative_path, _workspace_path


CODE_AST_EDIT_CAPABILITY = "code.ast_edit"


@dataclass(frozen=True)
class SelectedNode:
    node: Any
    path: tuple[int, ...]


def is_ast_edit_capability(capability_id: str) -> bool:
    return capability_id == CODE_AST_EDIT_CAPABILITY


def validate_ast_edit_inputs(
    *,
    capability_id: str,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    if capability_id != CODE_AST_EDIT_CAPABILITY:
        return dict(inputs or {})
    input_mapping = dict(inputs or {})
    for name in ("root", "cwd", "path", "replacement"):
        if name in missing_inputs:
            continue
        value = input_mapping.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
        input_mapping[name] = value if name == "replacement" else value.strip()
    if "path" not in missing_inputs:
        input_mapping["path"] = _safe_relative_path(
            input_mapping["path"],
            field_name="path",
        )
    if "selector" not in missing_inputs:
        input_mapping["selector"] = _validate_selector(input_mapping.get("selector"))
    language = input_mapping.get("language")
    if language is not None:
        if not isinstance(language, str) or not language.strip():
            raise ValueError("language must be a non-empty string")
        input_mapping["language"] = language.strip()
    return input_mapping


def run_code_ast_edit(*, inputs: Mapping[str, Any] | None) -> dict[str, Any]:
    required_inputs = ["root", "cwd", "path", "selector", "replacement"]
    missing_inputs = _missing_inputs(required_inputs, inputs)
    if missing_inputs:
        raise ValueError("missing required capability inputs: " + ", ".join(missing_inputs))
    input_mapping = validate_ast_edit_inputs(
        capability_id=CODE_AST_EDIT_CAPABILITY,
        inputs=inputs,
        missing_inputs=missing_inputs,
    )

    cwd = Path(input_mapping["cwd"]).expanduser()
    path = input_mapping["path"]
    target = _workspace_path(cwd, path, field_name="path")
    if not target.exists():
        raise ValueError("path must exist before AST edit")
    if not target.is_file():
        raise ValueError("path must name a file before AST edit")
    try:
        source_text = target.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("path must be utf-8 text") from exc

    language = _language_for_path(path, input_mapping.get("language"))
    source_bytes = source_text.encode("utf-8")
    root_node = _parse_root(source_text, language=language)
    if _node_has_error(root_node):
        raise ValueError("source file contains syntax errors")
    selected = _select_node(
        root_node,
        source_bytes=source_bytes,
        selector=input_mapping["selector"],
    )
    replacement = input_mapping["replacement"]
    replacement_bytes = replacement.encode("utf-8")
    new_source_bytes = (
        source_bytes[: _node_start_byte(selected.node)]
        + replacement_bytes
        + source_bytes[_node_end_byte(selected.node) :]
    )
    new_source_text = new_source_bytes.decode("utf-8")
    new_root_node = _parse_root(new_source_text, language=language)
    if _node_has_error(new_root_node):
        raise ValueError("replacement produces syntax errors")

    target.write_bytes(new_source_bytes)
    selected_summary = _node_summary(
        selected.node,
        path=selected.path,
        source_bytes=source_bytes,
    )
    return {
        "kind": "capability_run_result",
        "capability_id": CODE_AST_EDIT_CAPABILITY,
        "status": "completed",
        "runner_kind": "deterministic_local",
        "ast_edit": {
            "status": "applied",
            "path": path,
            "language": language,
            "parse_engine": "tree-sitter",
            "universal_tree": _tree_summary(root_node, selected_path=selected.path),
            "selected_node": selected_summary,
            "replacement": {
                "byte_count": len(replacement_bytes),
                "line_count": len(replacement.splitlines()),
                "text_sha256": sha256(replacement_bytes).hexdigest(),
            },
            "changed_files": [path],
            "syntax_check": {
                "status": "passed",
                "has_error": False,
                "root_type": _node_kind(new_root_node),
            },
            "write_policy": "workspace_relative_ast_node_replace",
            "content_policy": "node_ranges_and_hashes_only",
        },
    }


def _missing_inputs(
    required_inputs: list[str], inputs: Mapping[str, Any] | None
) -> list[str]:
    return missing_required_input_keys(inputs, required_inputs)


def _validate_selector(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("selector must be an object")
    selector = dict(value)
    node_path = selector.get("node_path")
    node_type = selector.get("node_type")
    text_contains = selector.get("text_contains")
    if node_path is not None:
        if not isinstance(node_path, list):
            raise ValueError("selector.node_path must be a list of integers")
        normalized_path: list[int] = []
        for index, item in enumerate(node_path):
            if not isinstance(item, int) or isinstance(item, bool) or item < 0:
                raise ValueError(f"selector.node_path[{index}] must be a non-negative integer")
            normalized_path.append(item)
        selector["node_path"] = normalized_path
    if node_type is not None:
        if not isinstance(node_type, str) or not node_type.strip():
            raise ValueError("selector.node_type must be a non-empty string")
        selector["node_type"] = node_type.strip()
    if text_contains is not None:
        if not isinstance(text_contains, str) or not text_contains:
            raise ValueError("selector.text_contains must be a non-empty string")
    occurrence = selector.get("occurrence", 1)
    if not isinstance(occurrence, int) or isinstance(occurrence, bool) or occurrence < 1:
        raise ValueError("selector.occurrence must be a positive integer")
    selector["occurrence"] = occurrence
    if node_path is None and node_type is None:
        raise ValueError("selector must include node_path or node_type")
    return selector


def _language_for_path(path: str, explicit_language: Any) -> str:
    if isinstance(explicit_language, str) and explicit_language.strip():
        return explicit_language.strip()
    try:
        detected = detect_language_from_path(path)
    except Exception as exc:
        raise ValueError("language could not be detected for path") from exc
    if not isinstance(detected, str) or not detected:
        raise ValueError("language could not be detected for path")
    return detected


def _parse_root(source_text: str, *, language: str) -> Any:
    try:
        tree = get_parser(language).parse(source_text)
    except Exception as exc:
        raise ValueError(f"tree-sitter parser unavailable for language: {language}") from exc
    root_node = tree.root_node
    return root_node() if callable(root_node) else root_node


def _select_node(root_node: Any, *, source_bytes: bytes, selector: Mapping[str, Any]) -> SelectedNode:
    node_path = selector.get("node_path")
    if isinstance(node_path, list):
        selected = _node_at_path(root_node, tuple(node_path))
        if not _selector_matches(selected, source_bytes=source_bytes, selector=selector):
            raise ValueError("selector did not match node_path target")
        return SelectedNode(node=selected, path=tuple(node_path))

    occurrence = int(selector.get("occurrence", 1))
    match_count = 0
    for candidate, candidate_path in _iter_named_nodes(root_node):
        if not _selector_matches(candidate, source_bytes=source_bytes, selector=selector):
            continue
        match_count += 1
        if match_count == occurrence:
            return SelectedNode(node=candidate, path=candidate_path)
    raise ValueError("selector did not match any syntax node")


def _node_at_path(root_node: Any, path: tuple[int, ...]) -> Any:
    node = root_node
    for item in path:
        child_count = _named_child_count(node)
        if item >= child_count:
            raise ValueError("selector.node_path does not exist")
        node = node.named_child(item)
    return node


def _selector_matches(node: Any, *, source_bytes: bytes, selector: Mapping[str, Any]) -> bool:
    node_type = selector.get("node_type")
    if isinstance(node_type, str) and _node_kind(node) != node_type:
        return False
    text_contains = selector.get("text_contains")
    if isinstance(text_contains, str) and text_contains not in _node_text(
        node,
        source_bytes=source_bytes,
    ):
        return False
    return True


def _iter_named_nodes(root_node: Any) -> Iterator[tuple[Any, tuple[int, ...]]]:
    yield root_node, ()
    for index in range(_named_child_count(root_node)):
        child = root_node.named_child(index)
        child_path = (index,)
        yield from _iter_named_nodes_with_path(child, child_path)


def _iter_named_nodes_with_path(node: Any, path: tuple[int, ...]) -> Iterator[tuple[Any, tuple[int, ...]]]:
    yield node, path
    for index in range(_named_child_count(node)):
        child = node.named_child(index)
        yield from _iter_named_nodes_with_path(child, (*path, index))


def _tree_summary(root_node: Any, *, selected_path: tuple[int, ...]) -> dict[str, Any]:
    stats = _tree_stats(root_node, depth=0)
    return {
        "root_type": _node_kind(root_node),
        "has_error": _node_has_error(root_node),
        "named_node_count": stats["named_node_count"],
        "max_depth": stats["max_depth"],
        "selected_path": list(selected_path),
        "projection": "universal_syntax_tree",
    }


def _tree_stats(node: Any, *, depth: int) -> dict[str, int]:
    named_node_count = 1
    max_depth = depth
    for index in range(_named_child_count(node)):
        child_stats = _tree_stats(node.named_child(index), depth=depth + 1)
        named_node_count += child_stats["named_node_count"]
        max_depth = max(max_depth, child_stats["max_depth"])
    return {"named_node_count": named_node_count, "max_depth": max_depth}


def _node_summary(
    node: Any,
    *,
    path: tuple[int, ...],
    source_bytes: bytes,
) -> dict[str, Any]:
    text = _node_text(node, source_bytes=source_bytes)
    return {
        "type": _node_kind(node),
        "path": list(path),
        "start_byte": _node_start_byte(node),
        "end_byte": _node_end_byte(node),
        "start_point": _point_tuple(node.start_position()),
        "end_point": _point_tuple(node.end_position()),
        "text_sha256": sha256(text.encode("utf-8")).hexdigest(),
        "has_error": _node_has_error(node),
    }


def _node_text(node: Any, *, source_bytes: bytes) -> str:
    return source_bytes[_node_start_byte(node) : _node_end_byte(node)].decode("utf-8")


def _node_kind(node: Any) -> str:
    kind = node.kind
    return str(kind() if callable(kind) else kind)


def _node_start_byte(node: Any) -> int:
    start_byte = node.start_byte
    return int(start_byte() if callable(start_byte) else start_byte)


def _node_end_byte(node: Any) -> int:
    end_byte = node.end_byte
    return int(end_byte() if callable(end_byte) else end_byte)


def _node_has_error(node: Any) -> bool:
    has_error = node.has_error
    return bool(has_error() if callable(has_error) else has_error)


def _named_child_count(node: Any) -> int:
    count = node.named_child_count
    return int(count() if callable(count) else count)


def _point_tuple(point: Any) -> list[int]:
    row = point.row
    column = point.column
    row_value = row() if callable(row) else row
    column_value = column() if callable(column) else column
    return [int(row_value), int(column_value)]


__all__ = [
    "CODE_AST_EDIT_CAPABILITY",
    "is_ast_edit_capability",
    "run_code_ast_edit",
    "validate_ast_edit_inputs",
]
