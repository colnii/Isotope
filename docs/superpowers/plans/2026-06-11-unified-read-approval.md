# Unified Read Approval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one Desktop-chat-facing read capability with workspace reads by default and approval-gated local-file reads.

**Architecture:** Implement the product-facing capability as `file.read` because the current catalog requires dotted capability IDs. Keep `code.read` as the legacy/internal workspace reader for existing native-coding flows, but make Desktop conversation prefer `file.read` and hide `code.read` from that model-facing manifest once `file.read` exists. Local-file reads create one approval-gated runtime action; approval resolution executes the read and returns a bounded artifact-backed result.

**Tech Stack:** Python 3.13, pytest, Svelte 5, TypeScript, Vitest, existing `CapabilityRunner`, `InProcessServer`, `Executor`, Desktop snapshot and approval UI.

---

## File Structure

Create focused read modules instead of adding more behavior to the already crowded `src/isotope/capabilities/` top level:

- Create `src/isotope/capabilities/read/__init__.py`: capability constants and exports.
- Create `src/isotope/capabilities/read/core.py`: input validation, bounded text read projection, workspace and local-file path normalization.
- Create `src/isotope/capabilities/read/runtime.py`: local-file approval request and local-file runtime tool execution helpers.
- Modify `src/isotope/capabilities/code_access.py`: reuse shared read projection helpers for existing `code.read`.
- Modify `src/isotope/capabilities/catalog.py`: add `file.read` product capability metadata.
- Modify `src/isotope/capabilities/runner.py`: validate and dispatch `file.read`.
- Modify `src/isotope/platform/registry/actions.py`: register `local_file_read` runtime tool.
- Modify `src/isotope/runtime/in_process/action_compiler.py`: validate `local_file_read` payload.
- Modify `src/isotope/execution/executor.py`: execute `local_file_read` via the new helper.
- Modify `src/isotope/features/supervisor/desktop_snapshot.py`: expose read-specific approval title and summary.
- Modify `apps/desktop/src/lib/components/main/ConversationWorkspace.svelte`: show local-file read path and excerpt limit in approval details.
- Modify `apps/desktop/src/lib/client/agentClient.ts` and `apps/desktop/src/lib/stores/appState.ts`: carry approval read result and append it to the chat after approval.
- Modify `src/isotope/features/supervisor/conversation_loop.py`: keep `file.read` in the Desktop capability manifest and suppress legacy `code.read` there.
- Modify `src/isotope/features/supervisor/conversation_observations.py`: summarize `file.read` results.
- Modify `src/isotope/llm/prompts/supervisor/conversation_loop.prompt.md`: instruct the model to use `file.read` for both scopes.

Use focused new tests:

- Create `tests/unit/capabilities/read/test_file_read_capability.py`.
- Create `tests/unit/runtime/in_process/test_local_file_read_approval.py`.
- Create `tests/unit/features/supervisor/conversation/test_file_read_conversation.py`.
- Create `tests/integration/supervisor/desktop/test_desktop_read_approval.py`.
- Modify `apps/desktop/src/lib/components/main/ConversationWorkspace.test.ts`.
- Modify `apps/desktop/src/lib/stores/appState.test.ts`.
- Modify `apps/desktop/src/lib/client/agentClient.test.ts`.

---

### Task 1: Add `file.read` Workspace Scope

**Files:**
- Create: `src/isotope/capabilities/read/__init__.py`
- Create: `src/isotope/capabilities/read/core.py`
- Modify: `src/isotope/capabilities/code_access.py`
- Modify: `src/isotope/capabilities/catalog.py`
- Modify: `src/isotope/capabilities/runner.py`
- Test: `tests/unit/capabilities/read/test_file_read_capability.py`

- [ ] **Step 1: Write failing workspace read tests**

Create `tests/unit/capabilities/read/test_file_read_capability.py`:

```python
from __future__ import annotations

import pytest

from isotope.capabilities.runner import CapabilityRunner


def test_file_read_workspace_scope_returns_bounded_excerpt(tmp_path) -> None:
    source = tmp_path / "src" / "app.py"
    source.parent.mkdir()
    source.write_text("marker = 'ISOTOPE_READ_MARKER'\n" * 20, encoding="utf-8")

    result = CapabilityRunner().run_capability(
        "file.read",
        inputs={
            "root": str(tmp_path / "state"),
            "cwd": str(tmp_path),
            "scope": "workspace",
            "path": "src/app.py",
            "max_excerpt_chars": 40,
        },
    )

    assert result["capability_id"] == "file.read"
    assert result["status"] == "completed"
    assert result["read"]["scope"] == "workspace"
    assert result["read"]["status"] == "readable"
    assert result["read"]["path"] == "src/app.py"
    assert result["read"]["truncated"] is True
    assert result["read"]["excerpt"] == "marker = 'ISOTOPE_READ_MARKER'\nmarker "
    assert result["read"]["ref"]["scope"] == "workspace"
    assert result["read"]["content_policy"] == "limited_excerpts_only"


def test_file_read_workspace_scope_rejects_workspace_escape(tmp_path) -> None:
    with pytest.raises(ValueError, match="path must stay inside the workspace"):
        CapabilityRunner().run_capability(
            "file.read",
            inputs={
                "root": str(tmp_path / "state"),
                "cwd": str(tmp_path),
                "scope": "workspace",
                "path": "../outside.md",
            },
        )


def test_file_read_local_file_scope_requires_root_for_approval(tmp_path) -> None:
    with pytest.raises(ValueError, match="root must be a non-empty string"):
        CapabilityRunner().run_capability(
            "file.read",
            inputs={
                "cwd": str(tmp_path),
                "scope": "local_file",
                "path": str(tmp_path / "note.md"),
            },
        )
```

- [ ] **Step 2: Run tests and verify they fail for the expected reason**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/capabilities/read/test_file_read_capability.py -q
```

Expected: failures mention unknown capability `file.read` or missing dispatch.

- [ ] **Step 3: Add read constants and shared projection helpers**

Create `src/isotope/capabilities/read/__init__.py`:

```python
"""Unified read capability exports."""

from __future__ import annotations

from .core import (
    FILE_READ_CAPABILITY,
    is_file_read_capability,
    read_text_excerpt,
    run_file_read,
    validate_file_read_inputs,
)

__all__ = [
    "FILE_READ_CAPABILITY",
    "is_file_read_capability",
    "read_text_excerpt",
    "run_file_read",
    "validate_file_read_inputs",
]
```

Create `src/isotope/capabilities/read/core.py`:

```python
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
        _validate_non_empty_strings(input_mapping, ("root",), missing_inputs)
    input_mapping["max_excerpt_chars"] = limited_int(
        input_mapping.get("max_excerpt_chars", _DEFAULT_MAX_EXCERPT_CHARS),
        field_name="max_excerpt_chars",
        minimum=1,
        maximum=_MAX_EXCERPT_CHARS,
    )
    return input_mapping


def run_file_read(*, inputs: Mapping[str, Any] | None) -> dict[str, Any]:
    required_inputs = ["scope", "path"]
    input_mapping = dict(inputs or {})
    if input_mapping.get("scope") == "workspace":
        required_inputs.extend(["root", "cwd"])
    elif input_mapping.get("scope") == "local_file":
        required_inputs.append("root")
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
```

- [ ] **Step 4: Wire catalog metadata**

In `src/isotope/capabilities/catalog.py`, add a `Capability(...)` entry near `code.read`:

```python
                Capability(
                    capability_id="file.read",
                    title="Read",
                    description=(
                        "Read one bounded text excerpt from either the current "
                        "workspace or an approval-gated local file path."
                    ),
                    maturity="v0.2",
                    shelf="product_candidate",
                    domain_tags=("read", "file", "workspace", "local-file", "inspection"),
                    input_contract={
                        "type": "object",
                        "required": ["root", "cwd", "scope", "path"],
                        "properties": {
                            "root": {
                                "type": "string",
                                "x-system-input": True,
                                "description": "Runtime root for approval and read artifacts.",
                            },
                            "cwd": {
                                "type": "string",
                                "x-system-input": True,
                                "description": "Workspace directory for workspace-scoped reads.",
                            },
                            "scope": {
                                "type": "string",
                                "enum": ["workspace", "local_file"],
                                "description": "Read boundary: workspace or approval-gated local_file.",
                            },
                            "path": {
                                "type": "string",
                                "description": "Workspace-relative path or approved local file path.",
                            },
                            "max_excerpt_chars": {
                                "type": "integer",
                                "description": "Maximum returned excerpt characters.",
                                "default": 2000,
                            },
                        },
                    },
                    output_contract={
                        "type": "object",
                        "fields": ["status", "runner_kind", "read", "approval_id"],
                    },
                    safety_boundaries=(
                        "workspace_scope_direct",
                        "local_file_scope_approval_required",
                        "single_file_only",
                        "limited_excerpts_only",
                        "no_write_delete_or_execute",
                        "public_result_metadata",
                    ),
                    default_enabled=True,
                    network_required=False,
                ),
```

- [ ] **Step 5: Wire `CapabilityRunner` validation and dispatch**

In `src/isotope/capabilities/runner.py`, import the new helpers:

```python
from .read import (
    FILE_READ_CAPABILITY,
    is_file_read_capability,
    run_file_read,
    validate_file_read_inputs,
)
```

Call `validate_file_read_inputs(...)` in both `plan_capability_run(...)` and `run_capability(...)` beside `validate_code_access_inputs(...)`.

Include `and not is_file_read_capability(capability_id)` in the allowlist rejection condition in `plan_capability_run(...)`.

Include `or is_file_read_capability(capability_id)` in the allowlisted execution group in `run_capability(...)`.

Dispatch before `CODE_READ_CAPABILITY`:

```python
        if capability_id == FILE_READ_CAPABILITY:
            return run_file_read(inputs=input_mapping)
```

- [ ] **Step 6: Reuse shared projection in `code.read`**

In `src/isotope/capabilities/code_access.py`, replace the body of `_read_text_excerpt(...)` with a wrapper around `read_text_excerpt(...)`:

```python
from .read.core import read_text_excerpt as _shared_read_text_excerpt
```

```python
def _read_text_excerpt(
    target: Path,
    *,
    path: str,
    max_excerpt_chars: int,
) -> dict[str, Any]:
    result = _shared_read_text_excerpt(
        target,
        path=path,
        scope="workspace",
        max_excerpt_chars=max_excerpt_chars,
    )
    if "ref" in result:
        result["code_ref"] = {
            **dict(result["ref"]),
            "ref_type": "code",
        }
        result.pop("ref", None)
    return result
```

Keep the existing `code.read` output shape stable for older tests.

- [ ] **Step 7: Run workspace read tests**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/capabilities/read/test_file_read_capability.py tests/unit/capabilities/test_core.py -q
```

Expected: all selected tests pass.

- [ ] **Step 8: Commit Task 1**

```bash
git add src/isotope/capabilities/read src/isotope/capabilities/code_access.py src/isotope/capabilities/catalog.py src/isotope/capabilities/runner.py tests/unit/capabilities/read/test_file_read_capability.py
git commit -m "feat(capabilities): add workspace scoped file read"
```

---

### Task 2: Add Approval-Gated Local File Runtime Action

**Files:**
- Create: `src/isotope/capabilities/read/runtime.py`
- Modify: `src/isotope/platform/registry/actions.py`
- Modify: `src/isotope/runtime/in_process/action_compiler.py`
- Modify: `src/isotope/execution/executor.py`
- Test: `tests/unit/runtime/in_process/test_local_file_read_approval.py`
- Test: `tests/unit/capabilities/read/test_file_read_capability.py`

- [ ] **Step 1: Add failing runtime approval tests**

Create `tests/unit/runtime/in_process/test_local_file_read_approval.py`:

```python
from __future__ import annotations

import json

from isotope.runtime.in_process import InProcessServer


def _create_run(root):
    api = InProcessServer(root)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="read local file")
    return api, run["run_id"]


def test_local_file_read_requires_approval_before_reading(tmp_path) -> None:
    target = tmp_path / "resume.md"
    target.write_text("private resume excerpt\n", encoding="utf-8")
    api, run_id = _create_run(tmp_path / "state")

    result = api.submit_action(
        run_id,
        {
            "action": "call_tool",
            "tool": "local_file_read",
            "path": str(target),
            "max_excerpt_chars": 2000,
            "summary": "Read one approved local file",
        },
        requires_approval=True,
    )

    assert result["status"] == "pending_user_approval"
    assert api.get_pending_approvals(run_id)[0]["status"] == "pending"
    artifact_dir = tmp_path / "state" / "runs" / run_id / "artifacts"
    assert not artifact_dir.exists()


def test_approved_local_file_read_writes_bounded_artifact(tmp_path) -> None:
    target = tmp_path / "resume.md"
    target.write_text("abcdef", encoding="utf-8")
    api, run_id = _create_run(tmp_path / "state")
    pending = api.submit_action(
        run_id,
        {
            "action": "call_tool",
            "tool": "local_file_read",
            "path": str(target),
            "max_excerpt_chars": 3,
            "summary": "Read one approved local file",
        },
        requires_approval=True,
    )

    resolved = api.resolve_approval(
        pending["approval_id"],
        {
            "resolution": "approved",
            "reason": "test approval",
            "resolver": "pytest",
        },
    )

    assert resolved["status"] == "completed"
    artifact_ref = resolved["artifact_ref"]
    content = api.artifact_store.get_content(artifact_ref)
    read = json.loads(content)
    assert read["scope"] == "local_file"
    assert read["status"] == "readable"
    assert read["excerpt"] == "abc"
    assert read["truncated"] is True


def test_denied_local_file_read_does_not_read_file(tmp_path) -> None:
    target = tmp_path / "resume.md"
    target.write_text("abcdef", encoding="utf-8")
    api, run_id = _create_run(tmp_path / "state")
    pending = api.submit_action(
        run_id,
        {
            "action": "call_tool",
            "tool": "local_file_read",
            "path": str(target),
            "max_excerpt_chars": 3,
            "summary": "Read one approved local file",
        },
        requires_approval=True,
    )

    resolved = api.resolve_approval(
        pending["approval_id"],
        {
            "resolution": "denied",
            "reason": "test denial",
            "resolver": "pytest",
        },
    )

    assert resolved["status"] == "denied"
    artifact_dir = tmp_path / "state" / "runs" / run_id / "artifacts"
    assert not artifact_dir.exists()
```

- [ ] **Step 2: Run tests and verify they fail for the expected reason**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/runtime/in_process/test_local_file_read_approval.py -q
```

Expected: failures mention unknown tool `local_file_read`.

- [ ] **Step 3: Implement local-file read runtime helper**

Create `src/isotope/capabilities/read/runtime.py`:

```python
"""Approval-gated local-file read runtime helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import json

from .core import FILE_READ_CAPABILITY, limited_int, read_text_excerpt


def request_local_file_read_approval(input_mapping: Mapping[str, Any]) -> dict[str, Any]:
    from isotope.runtime.in_process import InProcessServer

    root = Path(str(input_mapping["root"])).expanduser()
    path = str(input_mapping["path"])
    max_excerpt_chars = int(input_mapping["max_excerpt_chars"])
    api = InProcessServer(root)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal=f"Read local file: {path}")
    pending = api.submit_action(
        run["run_id"],
        {
            "action": "call_tool",
            "tool": "local_file_read",
            "path": path,
            "max_excerpt_chars": max_excerpt_chars,
            "summary": "Read one approved local file",
        },
        requires_approval=True,
    )
    return {
        "kind": "capability_run_result",
        "capability_id": FILE_READ_CAPABILITY,
        "status": "pending_user_approval",
        "runner_kind": "approval_gated_projection",
        "approval_id": pending["approval_id"],
        "read": {
            "scope": "local_file",
            "status": "pending_approval",
            "path": path,
            "approval_id": pending["approval_id"],
            "run_id": run["run_id"],
            "content_policy": "approval_required_before_read",
            "max_excerpt_chars": max_excerpt_chars,
        },
    }


def execute_local_file_read_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    path = payload.get("path")
    if not isinstance(path, str) or not path.strip():
        raise ValueError("path must be a non-empty string")
    max_excerpt_chars = limited_int(
        payload.get("max_excerpt_chars", 2000),
        field_name="max_excerpt_chars",
        minimum=1,
        maximum=8000,
    )
    target = Path(path).expanduser()
    return read_text_excerpt(
        target,
        path=str(target),
        scope="local_file",
        max_excerpt_chars=max_excerpt_chars,
    )


def local_file_read_artifact_content(read_result: dict[str, Any]) -> str:
    return json.dumps(read_result, ensure_ascii=False, sort_keys=True)
```

- [ ] **Step 4: Register `local_file_read` in the action registry**

In `src/isotope/platform/registry/actions.py`, include `_local_file_read_tool_entry()` in `ActionTypeRegistry.default(...)`:

```python
        entries = [
            _write_artifact_tool_entry(),
            _write_memory_tool_entry(),
            _terminal_exec_tool_entry(),
            _screen_observe_tool_entry(),
            _screen_control_tool_entry(),
            _local_file_read_tool_entry(),
        ]
```

Add:

```python
def _local_file_read_tool_entry() -> dict[str, Any]:
    return {
        "action_type": "call_tool",
        "tool_name": "local_file_read",
        "payload_requirements": {"required": ["path"]},
        "required_capabilities": {
            "tools": ["local_file_read"],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": 30},
        },
        "default_workspace_mode": "shared_ro",
        "result_kind": "artifact",
        "enabled": True,
    }
```

- [ ] **Step 5: Validate compiler payload**

In `src/isotope/runtime/in_process/action_compiler.py`, after the existing tool-specific payload blocks, add:

```python
        if tool == "local_file_read":
            path = payload.get("path")
            if not isinstance(path, str) or not path.strip():
                raise ValueError("local_file_read path must be a non-empty string")
            payload["path"] = path.strip()
            max_excerpt_chars = intent.get("max_excerpt_chars", 2000)
            if not isinstance(max_excerpt_chars, int) or isinstance(max_excerpt_chars, bool):
                raise ValueError("local_file_read max_excerpt_chars must be an integer")
            if max_excerpt_chars < 1 or max_excerpt_chars > 8000:
                raise ValueError("local_file_read max_excerpt_chars must be between 1 and 8000")
            payload["max_excerpt_chars"] = max_excerpt_chars
            payload["approval_requested"] = runtime_context.get("requires_approval") is True
```

- [ ] **Step 6: Execute local-file read after approval**

In `src/isotope/execution/executor.py`, import:

```python
from isotope.capabilities.read.runtime import (
    execute_local_file_read_payload,
    local_file_read_artifact_content,
)
```

Add an `elif tool_name == "local_file_read":` branch before the generic `elif tool_name != "write_artifact_tool":` branch:

```python
            elif tool_name == "local_file_read":
                self.workspace_manager.get_binding(decision.grants)
                execution = self._new_execution(execution_id, proposal, decision, status="completed")
                read_result = execute_local_file_read_payload(proposal.payload)
                artifact = self.artifact_store.create_artifact(
                    run_id=proposal.run_id,
                    execution_id=execution.execution_id,
                    artifact_type="local_file_read",
                    summary=f"local file read: {read_result.get('path', '')}",
                    content=local_file_read_artifact_content(read_result),
                    proposal_id=proposal.proposal_id,
                    decision_id=decision.decision_id,
                    source_refs=[dict(read_result["ref"])] if isinstance(read_result.get("ref"), dict) else [],
                )
                artifact_refs = [artifact.ref]
                completion_metadata = {
                    "local_file_read": {
                        "status": read_result.get("status"),
                        "path": read_result.get("path"),
                        "truncated": read_result.get("truncated"),
                    }
                }
```

- [ ] **Step 7: Extend file.read tests for pending approval**

Append to `tests/unit/capabilities/read/test_file_read_capability.py`:

```python
def test_file_read_local_file_scope_creates_pending_approval(tmp_path) -> None:
    target = tmp_path / "resume.md"
    target.write_text("resume text\n", encoding="utf-8")

    result = CapabilityRunner().run_capability(
        "file.read",
        inputs={
            "root": str(tmp_path / "state"),
            "cwd": str(tmp_path / "workspace"),
            "scope": "local_file",
            "path": str(target),
            "max_excerpt_chars": 2000,
        },
    )

    assert result["status"] == "pending_user_approval"
    assert result["approval_id"].startswith("approval_")
    assert result["read"]["scope"] == "local_file"
    assert result["read"]["status"] == "pending_approval"
    assert result["read"]["path"] == str(target)
```

- [ ] **Step 8: Run Task 2 tests**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/capabilities/read/test_file_read_capability.py tests/unit/runtime/in_process/test_local_file_read_approval.py -q
```

Expected: all selected tests pass.

- [ ] **Step 9: Commit Task 2**

```bash
git add src/isotope/capabilities/read/runtime.py src/isotope/platform/registry/actions.py src/isotope/runtime/in_process/action_compiler.py src/isotope/execution/executor.py tests/unit/runtime/in_process/test_local_file_read_approval.py tests/unit/capabilities/read/test_file_read_capability.py
git commit -m "feat(runtime): approve local file reads"
```

---

### Task 3: Surface Read Approval In Desktop Snapshot And Frontend

**Files:**
- Modify: `src/isotope/features/supervisor/desktop_snapshot.py`
- Modify: `src/isotope/features/supervisor/web/_impl.py`
- Modify: `apps/desktop/src/lib/contracts/isotope.ts`
- Modify: `apps/desktop/src/lib/client/agentClient.ts`
- Modify: `apps/desktop/src/lib/stores/appState.ts`
- Modify: `apps/desktop/src/lib/components/main/ConversationWorkspace.svelte`
- Test: `tests/integration/supervisor/desktop/test_desktop_read_approval.py`
- Test: `apps/desktop/src/lib/client/agentClient.test.ts`
- Test: `apps/desktop/src/lib/stores/appState.test.ts`
- Test: `apps/desktop/src/lib/components/main/ConversationWorkspace.test.ts`

- [ ] **Step 1: Add failing backend desktop snapshot test**

Create `tests/integration/supervisor/desktop/test_desktop_read_approval.py`:

```python
from __future__ import annotations

from isotope.features.supervisor.desktop_snapshot import build_desktop_snapshot
from isotope.runtime.in_process import InProcessServer


def test_desktop_snapshot_projects_local_file_read_approval(tmp_path) -> None:
    target = tmp_path / "resume.md"
    target.write_text("resume text\n", encoding="utf-8")
    root = tmp_path / "state"
    api = InProcessServer(root)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="read local file")
    pending = api.submit_action(
        run["run_id"],
        {
            "action": "call_tool",
            "tool": "local_file_read",
            "path": str(target),
            "max_excerpt_chars": 123,
            "summary": "Read one approved local file",
        },
        requires_approval=True,
    )

    snapshot = build_desktop_snapshot(state_root=root)

    approval = next(item for item in snapshot["approvals"] if item["id"] == pending["approval_id"])
    assert approval["title"] == "读取本地文件"
    assert approval["requestedActionSummary"] == {
        "tool": "local_file_read",
        "path": str(target),
        "max_excerpt_chars": 123,
        "scope": "local_file",
    }
```

- [ ] **Step 2: Run backend snapshot test and verify it fails**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/integration/supervisor/desktop/test_desktop_read_approval.py -q
```

Expected: failure shows missing `requestedActionSummary` or generic title.

- [ ] **Step 3: Project read approval summary**

In `src/isotope/features/supervisor/desktop_snapshot.py`, include both legacy label and frontend summary:

```python
def _runtime_approval_card(approval: dict[str, Any]) -> dict[str, Any]:
    approval_id = str(approval["approval_id"])
    requested_label = _public_metadata_mapping(
        approval.get("requested_action_label"),
    )
    requested_summary = _runtime_approval_summary(requested_label)
    title = _runtime_approval_title(requested_label)
    source_ref = {"kind": "approval", "id": approval_id, "label": title}
    return _omit_none({
        "id": approval_id,
        "title": title,
        "status": "pending",
        "riskLevel": "medium",
        "runId": approval.get("run_id"),
        "proposalId": approval.get("proposal_id"),
        "decisionId": approval.get("decision_id"),
        "reasonCodes": list(approval.get("reason_codes", [])),
        "requestedActionLabel": requested_label,
        "requestedActionSummary": requested_summary,
        "source": {
            "kind": "derived",
            "label": "runtime_approval_request",
            "sourceRef": source_ref,
        },
    })
```

Add:

```python
def _runtime_approval_summary(requested_label: dict[str, Any] | None) -> dict[str, Any] | None:
    tool = _label_string(requested_label, "tool")
    if tool == "local_file_read":
        path = _label_string(requested_label, "path")
        max_excerpt_chars = requested_label.get("max_excerpt_chars") if isinstance(requested_label, dict) else None
        summary: dict[str, Any] = {"tool": tool, "scope": "local_file"}
        if path:
            summary["path"] = path
        if isinstance(max_excerpt_chars, int) and not isinstance(max_excerpt_chars, bool):
            summary["max_excerpt_chars"] = max_excerpt_chars
        return summary
    if requested_label is None:
        return None
    return dict(requested_label)
```

Update `_runtime_approval_title(...)`:

```python
    if tool == "local_file_read":
        return "读取本地文件"
```

- [ ] **Step 4: Return read result from desktop approval resolve**

In `src/isotope/features/supervisor/web/_impl.py`, extend `resolve_desktop_approval_payload(...)`:

```python
        response = {
            "status": "ok",
            "approvalId": approval_id,
            "resolution": resolution,
            "runStatus": getattr(run_state, "status", str(result.get("status", "unknown"))),
            "snapshot": self.desktop_snapshot_payload(),
        }
        read_result = _local_file_read_result_from_resolution(
            InProcessServer(self.codex_home),
            result,
        )
        if read_result is not None:
            response["readResult"] = read_result
        return response
```

Add helper near other private helpers:

```python
def _local_file_read_result_from_resolution(
    api: InProcessServer,
    result: dict[str, Any],
) -> dict[str, Any] | None:
    artifact_ref = result.get("artifact_ref")
    if artifact_ref is None:
        return None
    metadata = api.artifact_store.get_metadata(artifact_ref)
    if metadata.get("artifact_type") != "local_file_read":
        return None
    try:
        content = json.loads(api.artifact_store.get_content(artifact_ref))
    except json.JSONDecodeError:
        return None
    if not isinstance(content, dict):
        return None
    return content
```

- [ ] **Step 5: Add frontend contract and client tests**

In `apps/desktop/src/lib/contracts/isotope.ts`, add:

```ts
export type DesktopReadResult = {
  scope: 'workspace' | 'local_file';
  status: string;
  path: string;
  excerpt?: string;
  truncated?: boolean;
  byte_count?: number;
  line_count?: number;
  content_policy?: string;
};
```

In `apps/desktop/src/lib/client/agentClient.ts`, extend `DesktopApprovalResolutionResult`:

```ts
export type DesktopApprovalResolutionResult = {
  status: 'ok';
  approvalId: string;
  resolution: ApprovalResolution;
  runStatus: string;
  snapshot: IsotopeSnapshot;
  readResult?: DesktopReadResult;
};
```

Add to `apps/desktop/src/lib/client/agentClient.test.ts`:

```ts
  test('returns read result from desktop approval resolution', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        status: 'ok',
        approvalId: 'approval-1',
        resolution: 'approved',
        runStatus: 'completed',
        snapshot: snapshotFixture(),
        readResult: {
          scope: 'local_file',
          status: 'readable',
          path: '/tmp/resume.md',
          excerpt: 'resume text',
          truncated: false
        }
      })
    }));
    vi.stubGlobal('fetch', fetchMock);

    const result = await createAgentClient('http://127.0.0.1:8765').resolveApproval(
      'approval-1',
      'approved',
      'operator approved'
    );

    expect(result.readResult?.path).toBe('/tmp/resume.md');
    expect(result.readResult?.excerpt).toBe('resume text');
  });
```

- [ ] **Step 6: Append approved read result to Desktop chat**

In `apps/desktop/src/lib/stores/appState.ts`, after `snapshot.set(result.snapshot);` in `resolveApproval(...)`, add:

```ts
        if (resolution === 'approved' && result.readResult) {
          appendApprovedReadResult(chatMessages, result.readResult);
        }
```

Add helper:

```ts
function appendApprovedReadResult(
  chatMessages: ReturnType<typeof writable<DesktopChatMessage[]>>,
  readResult: { path: string; excerpt?: string; truncated?: boolean; status: string }
) {
  const excerpt = typeof readResult.excerpt === 'string' ? readResult.excerpt : '';
  const suffix = readResult.truncated ? '\n\n[内容已截断]' : '';
  const text =
    readResult.status === 'readable'
      ? `已读取本地文件：${readResult.path}\n\n${excerpt}${suffix}`
      : `本地文件读取未完成：${readResult.path} (${readResult.status})`;
  chatMessages.update((messages) => [
    ...messages,
    {
      id: `chat_approval_read_${Date.now()}`,
      role: 'assistant',
      content: text,
      parts: [{ id: `chat_approval_read_text_${Date.now()}`, kind: 'text', text }],
    },
  ]);
}
```

Add to `apps/desktop/src/lib/stores/appState.test.ts`:

```ts
  test('appends approved local file read result to desktop chat', async () => {
    const state = createAppState({
      agentClient: {
        loadSnapshot: async () => realSnapshot(),
        loadScreenArtifactContent: async () => { throw new Error('not used'); },
        resolveApproval: async () => ({
          status: 'ok',
          approvalId: 'approval-1',
          resolution: 'approved',
          runStatus: 'completed',
          snapshot: realSnapshot(),
          readResult: {
            scope: 'local_file',
            status: 'readable',
            path: '/tmp/resume.md',
            excerpt: 'resume text',
            truncated: false
          }
        }),
        askDesktopQuestion: async () => ({ question: '', answer: '' })
      }
    });

    await state.resolveApproval('approval-1', 'approved');

    expect(get(state.chatMessages).at(-1)?.content).toContain('已读取本地文件：/tmp/resume.md');
    expect(get(state.chatMessages).at(-1)?.content).toContain('resume text');
  });
```

- [ ] **Step 7: Show local-file detail in approval card**

In `apps/desktop/src/lib/components/main/ConversationWorkspace.svelte`, extend `approvalDetail(...)`:

```ts
    const path = typeof summary.path === 'string' ? summary.path : null;
    const maxExcerptChars =
      typeof summary.max_excerpt_chars === 'number' ? summary.max_excerpt_chars : null;
    if (tool === 'local_file_read' && path) {
      return maxExcerptChars === null ? path : `${path} / 最多 ${maxExcerptChars} 字符`;
    }
```

Append to `apps/desktop/src/lib/components/main/ConversationWorkspace.test.ts`:

```ts
  test('contains local file read approval detail branch', () => {
    const path = join(process.cwd(), 'src/lib/components/main/ConversationWorkspace.svelte');
    const source = readFileSync(path, 'utf8');

    expect(source).toContain("tool === 'local_file_read'");
    expect(source).toContain('最多 ${maxExcerptChars} 字符');
  });
```

- [ ] **Step 8: Run Task 3 tests**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/integration/supervisor/desktop/test_desktop_read_approval.py -q
cd apps/desktop && npm test -- src/lib/client/agentClient.test.ts src/lib/stores/appState.test.ts src/lib/components/main/ConversationWorkspace.test.ts
```

Expected: all selected tests pass.

- [ ] **Step 9: Commit Task 3**

```bash
git add src/isotope/features/supervisor/desktop_snapshot.py src/isotope/features/supervisor/web/_impl.py apps/desktop/src/lib/contracts/isotope.ts apps/desktop/src/lib/client/agentClient.ts apps/desktop/src/lib/stores/appState.ts apps/desktop/src/lib/components/main/ConversationWorkspace.svelte tests/integration/supervisor/desktop/test_desktop_read_approval.py apps/desktop/src/lib/client/agentClient.test.ts apps/desktop/src/lib/stores/appState.test.ts apps/desktop/src/lib/components/main/ConversationWorkspace.test.ts
git commit -m "feat(desktop): resolve local file read approvals"
```

---

### Task 4: Teach Desktop Conversation To Use `file.read`

**Files:**
- Modify: `src/isotope/features/supervisor/conversation_loop.py`
- Modify: `src/isotope/features/supervisor/conversation_observations.py`
- Modify: `src/isotope/llm/prompts/supervisor/conversation_loop.prompt.md`
- Test: `tests/unit/features/supervisor/conversation/test_file_read_conversation.py`

- [ ] **Step 1: Write failing conversation tests**

Create `tests/unit/features/supervisor/conversation/test_file_read_conversation.py`:

```python
from __future__ import annotations

import json
from typing import Any

from isotope.features.supervisor import conversation_loop
from isotope.features.supervisor.conversation_loop import run_supervisor_conversation_events
from isotope.llm.provider import LLMResponse


class RecordingProvider:
    provider = "deterministic_test"
    model = "file-read-conversation"

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def generate(self, messages: list[dict[str, str]], *, max_tokens: int = 512) -> LLMResponse:
        self.calls.append({"messages": messages, "max_tokens": max_tokens})
        return LLMResponse(
            provider=self.provider,
            model=self.model,
            content=json.dumps(self.responses.pop(0), ensure_ascii=False),
            finish_reason="stop",
            usage={},
            raw={},
        )


def test_desktop_manifest_prefers_file_read_over_legacy_code_read(tmp_path) -> None:
    provider = RecordingProvider([
        {
            "kind": "direct_answer",
            "answer_basis": {"kind": "no_capability_needed", "reason": "inspect manifest"},
            "answer": "ok",
        }
    ])

    list(
        run_supervisor_conversation_events(
            state_root=tmp_path / "state",
            cwd=tmp_path,
            user_message="hello",
            provider=provider,
            max_turns=1,
        )
    )

    prompt = provider.calls[0]["messages"][0]["content"]
    assert '"capability_id": "file.read"' in prompt
    assert '"capability_id": "code.read"' not in prompt


def test_file_read_observation_is_available_for_final_answer(tmp_path, monkeypatch) -> None:
    target = tmp_path / "note.md"
    target.write_text("hello from local note", encoding="utf-8")

    def fake_execute_capacity_step(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["capability_id"] == "file.read"
        return {
            "tick_result": {
                "planner_result": {
                    "step_result": {
                        "action_result": {
                            "capability_run": {
                                "kind": "capability_run_result",
                                "capability_id": "file.read",
                                "status": "completed",
                                "read": {
                                    "scope": "workspace",
                                    "status": "readable",
                                    "path": "note.md",
                                    "excerpt": "hello from local note",
                                    "truncated": False,
                                    "content_policy": "limited_excerpts_only",
                                },
                            }
                        }
                    }
                }
            }
        }

    monkeypatch.setattr(
        conversation_loop,
        "_execute_capacity_step_with_timeout",
        fake_execute_capacity_step,
    )
    provider = RecordingProvider(
        [
            {
                "kind": "call_capability",
                "capacity_id": "file.read",
                "arguments": {"scope": "workspace", "path": "note.md"},
                "rationale": "需要读取 workspace 文件。",
            },
            {
                "kind": "direct_answer",
                "answer_basis": {"kind": "observation", "capacity_ids": ["file.read"]},
                "answer": "文件内容包含 hello from local note。",
            },
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path / "state",
            cwd=tmp_path,
            user_message="读 note.md",
            provider=provider,
            max_turns=3,
        )
    )

    assert [event.event for event in events] == ["capacity_start", "capacity_result", "delta"]
    second_prompt = json.dumps(provider.calls[1]["messages"], ensure_ascii=False)
    assert "file_read" in second_prompt
    assert "hello from local note" in second_prompt
    assert events[-1].payload["text"] == "文件内容包含 hello from local note。"
```

- [ ] **Step 2: Run conversation tests and verify they fail**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/supervisor/conversation/test_file_read_conversation.py -q
```

Expected: failures show legacy `code.read` still appears and `file.read` has no observation formatter.

- [ ] **Step 3: Filter legacy `code.read` out of Desktop conversation manifest**

In `src/isotope/features/supervisor/conversation_loop.py`, replace the current capability list comprehension in `_conversation_context(...)` with:

```python
    raw_capabilities = runner.list_capabilities()
    has_file_read = any(
        capability.get("capability_id") == "file.read"
        for capability in raw_capabilities
    )
    capabilities = [
        {
            "capability_id": capability.get("capability_id"),
            "title": capability.get("title"),
            "description": capability.get("description"),
            "shelf": capability.get("shelf"),
            "domain_tags": capability.get("domain_tags"),
            **_conversation_capability_projection(capability),
        }
        for capability in raw_capabilities
        if not (has_file_read and capability.get("capability_id") == "code.read")
    ]
```

- [ ] **Step 4: Add `file.read` observation formatter**

In `src/isotope/features/supervisor/conversation_observations.py`, add `file.read` label:

```python
        "file.read": "File read result",
```

Add dispatch:

```python
    if capacity_id == "file.read":
        return _file_read_observation(capability_run)
```

Add helper near `_code_read_observation(...)`:

```python
def _file_read_observation(capability_run: dict[str, Any]) -> dict[str, Any] | None:
    read = capability_run.get("read")
    if not isinstance(read, dict):
        return None
    return {
        key: value
        for key, value in {
            "kind": "file_read",
            "scope": read.get("scope"),
            "status": read.get("status"),
            "path": read.get("path"),
            "excerpt": read.get("excerpt"),
            "truncated": read.get("truncated"),
            "content_policy": read.get("content_policy"),
            "approval_id": read.get("approval_id"),
            "run_id": read.get("run_id"),
        }.items()
        if isinstance(value, (str, bool))
    }
```

- [ ] **Step 5: Update prompt guidance**

In `src/isotope/llm/prompts/supervisor/conversation_loop.prompt.md`, add a short rule to the capability-use guidance:

```markdown
- For reading files, prefer `file.read`. Use `scope="workspace"` for workspace-relative paths. Use `scope="local_file"` for absolute, UNC, or otherwise outside-workspace paths; that scope will request operator approval instead of reporting a capability gap.
```

- [ ] **Step 6: Run Task 4 tests**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/supervisor/conversation/test_file_read_conversation.py tests/unit/features/supervisor/test_conversation_loop_direct_answer_guard.py -q
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit Task 4**

```bash
git add src/isotope/features/supervisor/conversation_loop.py src/isotope/features/supervisor/conversation_observations.py src/isotope/llm/prompts/supervisor/conversation_loop.prompt.md tests/unit/features/supervisor/conversation/test_file_read_conversation.py
git commit -m "feat(supervisor): prefer unified file read in chat"
```

---

### Task 5: Add Desktop End-To-End Read Approval Regression

**Files:**
- Test: `tests/integration/supervisor/desktop/test_desktop_read_approval.py`

- [ ] **Step 1: Add an end-to-end approval resolve test**

Append to `tests/integration/supervisor/desktop/test_desktop_read_approval.py`:

```python
from isotope.features.supervisor.web import create_dashboard_server
import http.client
import json
import threading


def test_desktop_approval_resolve_returns_local_file_read_result(tmp_path) -> None:
    target = tmp_path / "resume.md"
    target.write_text("resume body", encoding="utf-8")
    root = tmp_path / "state"
    api = InProcessServer(root)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="read local file")
    pending = api.submit_action(
        run["run_id"],
        {
            "action": "call_tool",
            "tool": "local_file_read",
            "path": str(target),
            "max_excerpt_chars": 2000,
            "summary": "Read one approved local file",
        },
        requires_approval=True,
    )
    server = create_dashboard_server(
        codex_home=root,
        host="127.0.0.1",
        port=0,
        limit=5,
        stale_after_seconds=999999,
        active_within_seconds=180,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request(
            "POST",
            f"/desktop/approvals/{pending['approval_id']}/resolve",
            body=json.dumps(
                {
                    "resolution": "approved",
                    "reason": "approve local file read",
                    "resolver": "pytest",
                }
            ),
            headers={"content-type": "application/json"},
        )
        response = conn.getresponse()
        body = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert response.status == 200
    assert body["readResult"]["scope"] == "local_file"
    assert body["readResult"]["path"] == str(target)
    assert body["readResult"]["excerpt"] == "resume body"
    assert body["snapshot"]["counts"]["approvals"] == 0
```

- [ ] **Step 2: Run the integration regression**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/integration/supervisor/desktop/test_desktop_read_approval.py -q
```

Expected: all tests in the file pass.

- [ ] **Step 3: Commit Task 5**

```bash
git add tests/integration/supervisor/desktop/test_desktop_read_approval.py
git commit -m "test(desktop): cover local file read approval"
```

---

### Task 6: Full Targeted Verification And Cleanup

**Files:**
- No new source files unless prior tasks reveal a compile failure.

- [ ] **Step 1: Run Python targeted regression**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/capabilities/read/test_file_read_capability.py tests/unit/runtime/in_process/test_local_file_read_approval.py tests/unit/features/supervisor/conversation/test_file_read_conversation.py tests/integration/supervisor/desktop/test_desktop_read_approval.py tests/unit/features/supervisor/test_conversation_loop_direct_answer_guard.py tests/integration/supervisor/desktop/test_supervisor_desktop_chat.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run Desktop frontend targeted regression**

Run:

```bash
cd apps/desktop && npm test -- src/lib/client/agentClient.test.ts src/lib/stores/appState.test.ts src/lib/components/main/ConversationWorkspace.test.ts
```

Expected: selected Vitest files pass.

- [ ] **Step 3: Run frontend type check**

Run:

```bash
cd apps/desktop && npm run check
```

Expected: Svelte check exits 0.

- [ ] **Step 4: Check git diff hygiene**

Run:

```bash
git diff --check
git status --short --branch
```

Expected: `git diff --check` exits 0. `git status` shows only intentional tracked changes before the final commit, or a clean worktree after the final commit.

- [ ] **Step 5: Commit any verification-only fixes**

If Step 1, 2, or 3 required small compile/test fixes, commit them:

```bash
git add src tests apps/desktop/src
git commit -m "fix: stabilize unified read approval flow"
```

- [ ] **Step 6: Push implementation branch**

Run:

```bash
git push -u origin feat/unified-read-approval
```

Expected: branch pushes successfully and GitHub prints a PR creation URL.

---

## Self-Review

Spec coverage:

- One user-facing read action: covered by `file.read` manifest and Desktop conversation filtering.
- Workspace read direct path: covered by Task 1.
- Local-file one-time approval: covered by Task 2.
- Reuse Desktop approval endpoint and panel: covered by Task 3 and Task 5.
- Conversation behavior and no capability gap for external paths: covered by Task 4.
- Bounded text excerpts and metadata: covered by Task 1 and Task 2.
- Tests for backend, conversation, Desktop snapshot, frontend client/state/UI: covered by Tasks 1 through 6.

Type consistency:

- Capability ID is `file.read`.
- Runtime tool name is `local_file_read`.
- Unified capability result key is `read`.
- Frontend approval response key is `readResult`.
- Approval summary key is `requestedActionSummary`.

Scope check:

- Permanent grants, recursive directory reads, binary projection, write/delete/execute behavior, and search replacement remain outside this plan.
