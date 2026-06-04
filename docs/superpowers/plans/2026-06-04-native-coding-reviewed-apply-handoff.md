# Native Coding Reviewed Apply Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let native coding produce a review handle that the existing Supervisor conversation loop can use to apply the verified isolated diff without asking the model or user to fill `cwd`, `root`, `workspace_id`, or digest maps.

**Architecture:** Reuse the existing `coding_task.run`, `coding_task.execute`, `coding_task.apply_reviewed_diff`, `ArtifactStore`, and Supervisor conversation loop. `coding_task.execute` writes a low-sensitive reviewed-apply request artifact; `coding_task.apply_reviewed_diff` can resolve that artifact by `review_handle_id`; Supervisor observations expose only the handle, path counts, and suggested next capability call.

**Tech Stack:** Python 3.13, pytest, existing `CapabilityRunner`, `ArtifactStore`, native coding adapter, Supervisor capacity summaries, model-facing capacity observations.

---

## Scope

In scope:

- Add a persisted reviewed-apply handle for verified native coding executions.
- Keep `root` and `cwd` as system inputs.
- Stop requiring the model to author `workspace_id` and `expected_source_digests` for normal apply flow.
- Preserve the existing explicit apply step. No auto-apply.
- Keep raw patch, raw argv, raw file content, and full source text out of public summaries.

Out of scope:

- Auto commit, push, or merge.
- Deletion support in apply.
- A new coding agent loop.
- Broad UI redesign.

## File Structure

- Modify `src/isotope/capabilities/coding_execute.py`
  - Create a `native_coding.reviewed_apply_request` artifact after successful isolated execution.
  - Return a `review_handle_id` and artifact ref in `coding_execution.reviewed_apply`.
- Modify `src/isotope/capabilities/coding_apply.py`
  - Accept `review_handle_id`.
  - Resolve `workspace_id`, `expected_source_digests`, and `expected_changed_files` from the artifact.
  - Keep existing direct inputs for tests and backwards compatibility.
- Modify `src/isotope/capabilities/catalog.py`
  - Add `review_handle_id` to `coding_task.apply_reviewed_diff`.
  - Mark `workspace_id` and `expected_source_digests` as system/private apply inputs.
- Modify `src/isotope/features/supervisor/native_coding_run.py`
  - Bubble the latest reviewed-apply handle out of the native coding agent-loop result.
- Modify `src/isotope/features/supervisor/commands/capacity_summary.py`
  - Summarize handle availability and changed-file count.
- Modify `src/isotope/features/supervisor/conversation_observations.py`
  - Add a model-facing `suggested_next_call` for `coding_task.apply_reviewed_diff` using only `review_handle_id`.
- Modify `src/isotope/features/supervisor/conversation_loop.py`
  - Ensure apply input summaries hide `root`, `cwd`, `workspace_id`, and digest maps.
- Tests:
  - `tests/unit/capabilities/test_capability_runner_thin_shell.py`
  - `tests/unit/features/supervisor/test_supervisor_conversation_loop.py`
  - `tests/unit/features/supervisor/test_capacity_module_boundaries.py`

## Task 1: Persist A Reviewed-Apply Handle

**Files:**
- Modify: `src/isotope/capabilities/coding_execute.py`
- Test: `tests/unit/capabilities/test_capability_runner_thin_shell.py`

- [ ] **Step 1: Write the failing test**

Append this assertion block to `test_runner_executes_native_coding_task_in_isolated_workspace` after `reviewed_apply = execution["reviewed_apply"]`:

```python
    assert reviewed_apply["review_handle_id"]
    assert reviewed_apply["review_handle_ref"]["ref_type"] == "artifact"
    handle_content = json.loads(
        ArtifactStore(root).get_content(reviewed_apply["review_handle_id"])
    )
    assert handle_content == {
        "kind": "native_coding_reviewed_apply_request",
        "workspace_id": "workspace_native_coding_execute",
        "changed_files": ["src/app.py"],
        "expected_changed_files": ["src/app.py"],
        "expected_source_digests": reviewed_apply["expected_source_digests"],
        "include_paths": ["src"],
        "content_policy": "digest_and_path_only",
    }
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/capabilities/test_capability_runner_thin_shell.py::test_runner_executes_native_coding_task_in_isolated_workspace -q
```

Expected: fail because `review_handle_id` is not returned.

- [ ] **Step 3: Implement handle artifact creation**

In `src/isotope/capabilities/coding_execute.py`, after `changed_files` and `reviewed_apply_source_digests(...)` are computed, create one artifact:

```python
expected_source_digests = reviewed_apply_source_digests(
    cwd=input_mapping["cwd"],
    changed_files=[
        {"path": path, "status": "modified"} for path in changed_files
    ],
)
review_handle = ArtifactStore(root).create_artifact(
    input_mapping["run_id"],
    input_mapping["execution_id"],
    "native_coding.reviewed_apply_request",
    "Reviewed native coding apply request",
    json.dumps(
        {
            "kind": "native_coding_reviewed_apply_request",
            "workspace_id": input_mapping["workspace_id"],
            "changed_files": changed_files,
            "expected_changed_files": changed_files,
            "expected_source_digests": expected_source_digests,
            "include_paths": input_mapping["include_paths"],
            "content_policy": "digest_and_path_only",
        },
        sort_keys=True,
    ),
)
```

Use `expected_source_digests` in the existing `reviewed_apply` output and add:

```python
"review_handle_id": review_handle.artifact_id,
"review_handle_ref": review_handle.ref.to_dict(),
```

- [ ] **Step 4: Run the test and verify it passes**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/capabilities/test_capability_runner_thin_shell.py::test_runner_executes_native_coding_task_in_isolated_workspace -q
```

Expected: pass.

- [ ] **Step 5: Commit Task 1**

```bash
git add src/isotope/capabilities/coding_execute.py tests/unit/capabilities/test_capability_runner_thin_shell.py
git commit -m "feat(supervisor): persist native coding review handles"
```

## Task 2: Apply By Review Handle

**Files:**
- Modify: `src/isotope/capabilities/coding_apply.py`
- Modify: `src/isotope/capabilities/catalog.py`
- Test: `tests/unit/capabilities/test_capability_runner_thin_shell.py`

- [ ] **Step 1: Write the failing apply-by-handle test**

Add this test near `test_runner_applies_reviewed_native_coding_workspace_to_source`:

```python
def test_runner_applies_reviewed_native_coding_workspace_by_review_handle(tmp_path):
    source = tmp_path / "repo"
    (source / "src").mkdir(parents=True)
    (source / "src" / "app.py").write_text("value = 1\n", encoding="utf-8")
    root = tmp_path / "state"
    execute_result = _runner().run_capability(
        "coding_task.execute",
        inputs={
            "root": str(root),
            "cwd": str(source),
            "workspace_id": "workspace_native_apply_handle",
            "goal": "Change value to 2.",
            "patch": (
                "--- a/src/app.py\n"
                "+++ b/src/app.py\n"
                "@@ -1 +1 @@\n"
                "-value = 1\n"
                "+value = 2\n"
            ),
            "argv": [
                "python3",
                "-c",
                "from pathlib import Path; assert Path('src/app.py').read_text() == 'value = 2\\n'",
            ],
            "allowed_commands": ["python3"],
            "run_id": "run_native_apply_handle",
            "execution_id": "execution_native_apply_handle",
            "include_paths": ["src"],
        },
    )

    result = _runner().run_capability(
        "coding_task.apply_reviewed_diff",
        inputs={
            "root": str(root),
            "cwd": str(source),
            "review_handle_id": execute_result["coding_execution"]["reviewed_apply"][
                "review_handle_id"
            ],
        },
    )

    applied = result["reviewed_apply"]
    assert applied["status"] == "applied"
    assert applied["review_handle_id"]
    assert applied["applied_files"] == ["src/app.py"]
    assert (source / "src" / "app.py").read_text(encoding="utf-8") == "value = 2\n"
    assert "value = 2" not in json.dumps(applied, ensure_ascii=False)
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/capabilities/test_capability_runner_thin_shell.py::test_runner_applies_reviewed_native_coding_workspace_by_review_handle -q
```

Expected: fail because `review_handle_id` is not a supported apply input.

- [ ] **Step 3: Add contract support**

In `src/isotope/capabilities/catalog.py`, add this public property to `coding_task.apply_reviewed_diff`:

```python
"review_handle_id": {
    "type": "string",
    "description": "Reviewed native coding apply handle returned by coding_task.run or coding_task.execute.",
},
```

Keep `root`, `cwd`, `workspace_id`, and `expected_source_digests` in the internal contract. Mark `expected_source_digests` with `"x-system-input": True`.

- [ ] **Step 4: Resolve handle content in apply runner**

In `src/isotope/capabilities/coding_apply.py`, import `json`, `JSONDecodeError`, and `ArtifactStore`. Before required-input validation, resolve the handle:

```python
def _inputs_with_review_handle(inputs: Mapping[str, Any] | None) -> dict[str, Any]:
    input_mapping = dict(inputs or {})
    handle_id = input_mapping.get("review_handle_id")
    if not isinstance(handle_id, str) or not handle_id:
        return input_mapping
    root = input_mapping.get("root")
    if not isinstance(root, str) or not root:
        raise ValueError("root is required when review_handle_id is used")
    try:
        payload = json.loads(
            ArtifactStore(Path(root).expanduser()).get_content(handle_id)
        )
    except JSONDecodeError as exc:
        raise ValueError("review handle content must be JSON") from exc
    if not isinstance(payload, dict) or payload.get("kind") != "native_coding_reviewed_apply_request":
        raise ValueError("review_handle_id must reference a native coding reviewed apply request")
    for key in (
        "workspace_id",
        "expected_source_digests",
        "expected_changed_files",
        "include_paths",
    ):
        if key in payload and key not in input_mapping:
            input_mapping[key] = payload[key]
    return input_mapping
```

At the start of `run_coding_task_apply_reviewed_diff(...)`, use:

```python
input_mapping = _inputs_with_review_handle(inputs)
required_inputs = ["root", "cwd", "workspace_id", "expected_source_digests"]
missing_inputs = missing_required_input_keys(input_mapping, required_inputs)
```

Pass `input_mapping` into `validate_coding_apply_inputs(...)`.

Add `"review_handle_id": input_mapping.get("review_handle_id")` to both applied and blocked `reviewed_apply` payloads.

- [ ] **Step 5: Run apply tests**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/unit/capabilities/test_capability_runner_thin_shell.py::test_runner_discovers_coding_task_apply_reviewed_diff_from_default_catalog \
  tests/unit/capabilities/test_capability_runner_thin_shell.py::test_runner_applies_reviewed_native_coding_workspace_by_review_handle \
  tests/unit/capabilities/test_capability_runner_thin_shell.py::test_runner_applies_reviewed_native_coding_workspace_to_source \
  tests/unit/capabilities/test_capability_runner_thin_shell.py::test_reviewed_native_coding_apply_blocks_source_conflict_without_write \
  -q
```

Expected: all pass.

- [ ] **Step 6: Commit Task 2**

```bash
git add src/isotope/capabilities/coding_apply.py src/isotope/capabilities/catalog.py tests/unit/capabilities/test_capability_runner_thin_shell.py
git commit -m "feat(supervisor): apply native coding reviews by handle"
```

## Task 3: Expose The Handle To The Existing Conversation Loop

**Files:**
- Modify: `src/isotope/features/supervisor/native_coding_run.py`
- Modify: `src/isotope/features/supervisor/commands/capacity_summary.py`
- Modify: `src/isotope/features/supervisor/conversation_observations.py`
- Modify: `src/isotope/features/supervisor/conversation_loop.py`
- Test: `tests/unit/features/supervisor/test_supervisor_conversation_loop.py`
- Test: `tests/unit/features/supervisor/test_capacity_module_boundaries.py`

- [ ] **Step 1: Write the failing conversation handoff test**

In `test_conversation_loop_runs_coding_task_run_through_existing_agent_loop`, after `summary = events[1].payload["result_summary"]`, add:

```python
    assert summary["agent_loop_coding_review_handle_available"] is True
    assert summary["agent_loop_coding_reviewed_apply_capability_id"] == "coding_task.apply_reviewed_diff"
    assert summary["agent_loop_coding_reviewed_apply_changed_file_count"] == 1
    second_prompt = provider.calls[-1]["messages"][1]["content"]
    assert '"suggested_next_call"' in second_prompt
    assert '"coding_task.apply_reviewed_diff"' in second_prompt
    assert '"review_handle_id"' in second_prompt
    assert '"expected_source_digests"' not in second_prompt
    assert str(workspace) not in second_prompt
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/features/supervisor/test_supervisor_conversation_loop.py::test_conversation_loop_runs_coding_task_run_through_existing_agent_loop -q
```

Expected: fail because native coding summaries and observations do not expose a review handle yet.

- [ ] **Step 3: Bubble handle from native coding ticks**

In `src/isotope/features/supervisor/native_coding_run.py`, add:

```python
def _reviewed_apply_request(ticks: list[dict[str, Any]]) -> dict[str, Any] | None:
    for tick in reversed(ticks):
        execution = _coding_execution(tick)
        if not isinstance(execution, Mapping):
            continue
        reviewed_apply = execution.get("reviewed_apply")
        if not isinstance(reviewed_apply, Mapping):
            continue
        handle_id = reviewed_apply.get("review_handle_id")
        workspace_id = reviewed_apply.get("workspace_id")
        changed_files = reviewed_apply.get("changed_files")
        if not isinstance(handle_id, str) or not isinstance(workspace_id, str):
            continue
        return {
            "capability_id": "coding_task.apply_reviewed_diff",
            "arguments": {"review_handle_id": handle_id},
            "workspace_id": workspace_id,
            "changed_files": list(changed_files) if isinstance(changed_files, list) else [],
            "source_workspace_write": "requires_explicit_apply",
        }
    return None
```

Add to the returned native coding agent-loop dict:

```python
"reviewed_apply_request": _reviewed_apply_request(ticks),
```

- [ ] **Step 4: Summarize handle availability**

In `_agent_loop_native_coding_summary(...)` inside `src/isotope/features/supervisor/commands/capacity_summary.py`, compute:

```python
reviewed_apply = agent_loop.get("reviewed_apply_request")
changed_files = reviewed_apply.get("changed_files") if isinstance(reviewed_apply, Mapping) else []
```

Add these summary fields:

```python
"agent_loop_coding_review_handle_available": isinstance(reviewed_apply, Mapping),
"agent_loop_coding_reviewed_apply_capability_id": (
    reviewed_apply.get("capability_id") if isinstance(reviewed_apply, Mapping) else None
),
"agent_loop_coding_reviewed_apply_changed_file_count": (
    len(changed_files) if isinstance(changed_files, list) else 0
),
```

- [ ] **Step 5: Add model-facing suggested next call**

In `model_observation_from_agent_loop(...)` in `src/isotope/features/supervisor/conversation_observations.py`, after the `result` block, add:

```python
if capacity_id == "coding_task.run":
    reviewed_apply = agent_loop.get("reviewed_apply_request")
    if isinstance(reviewed_apply, dict):
        arguments = reviewed_apply.get("arguments")
        if isinstance(arguments, dict):
            observation["suggested_next_call"] = {
                "capacity_id": "coding_task.apply_reviewed_diff",
                "arguments": {
                    "review_handle_id": arguments.get("review_handle_id"),
                },
                "requires_user_approval": True,
            }
```

- [ ] **Step 6: Keep display inputs low-sensitive**

In `_capacity_display_inputs(...)` in `src/isotope/features/supervisor/conversation_loop.py`, for `coding_task.apply_reviewed_diff`, keep `review_handle_id` but remove `expected_source_digests`, `root`, `cwd`, and `workspace_id`:

```python
if capacity_id == "coding_task.apply_reviewed_diff":
    display.pop("root", None)
    display.pop("cwd", None)
    display.pop("workspace_id", None)
    display.pop("expected_source_digests", None)
    return display
```

- [ ] **Step 7: Run Supervisor tests**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/unit/features/supervisor/test_supervisor_conversation_loop.py::test_conversation_loop_runs_coding_task_run_through_existing_agent_loop \
  tests/unit/features/supervisor/test_supervisor_conversation_loop.py::test_conversation_loop_applies_reviewed_native_coding_diff \
  tests/unit/features/supervisor/test_capacity_module_boundaries.py \
  -q
```

Expected: all pass.

- [ ] **Step 8: Commit Task 3**

```bash
git add src/isotope/features/supervisor/native_coding_run.py src/isotope/features/supervisor/commands/capacity_summary.py src/isotope/features/supervisor/conversation_observations.py src/isotope/features/supervisor/conversation_loop.py tests/unit/features/supervisor/test_supervisor_conversation_loop.py tests/unit/features/supervisor/test_capacity_module_boundaries.py
git commit -m "feat(supervisor): expose native coding apply handoff"
```

## Task 4: Final Verification And Merge

**Files:**
- No new source files.

- [ ] **Step 1: Run focused verification**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/unit/interfaces/http/test_input_contract_schema.py \
  tests/unit/capabilities/test_capability_runner_thin_shell.py \
  tests/unit/capabilities/test_capability_catalog_shelves.py \
  tests/unit/features/supervisor/test_supervisor_conversation_loop.py \
  tests/unit/features/supervisor/test_capacity_module_boundaries.py \
  -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run formatting and leak checks**

Run:

```bash
git diff --check
rg -n '"patch"|"argv"|raw_response|raw_content|transcript|value = 2|expected_source_digests' src/isotope/features/supervisor tests/unit/features/supervisor/test_supervisor_conversation_loop.py tests/unit/capabilities/test_capability_runner_thin_shell.py
```

Expected: `git diff --check` exits 0. Search hits are limited to tests, existing redaction/filter code, or digest-only handle internals; public summaries and model observations must not expose raw patch, raw argv, raw content, root, or cwd.

- [ ] **Step 3: Commit final verification note if needed**

If only source/test commits exist, do not create an empty commit. If docs need correction, commit:

```bash
git add docs/superpowers/plans/2026-06-04-native-coding-reviewed-apply-handoff.md
git commit -m "docs: plan native coding apply handoff"
```

- [ ] **Step 4: Merge and cleanup**

Use the normal project workflow: rebase on latest `origin/main`, rerun focused verification, push to `main` if fast-forward, then remove the temporary worktree and branch.

Commands:

```bash
git fetch origin main
git rebase origin/main
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/capabilities/test_capability_runner_thin_shell.py tests/unit/features/supervisor/test_supervisor_conversation_loop.py tests/unit/features/supervisor/test_capacity_module_boundaries.py -q
git push origin HEAD:main
git worktree remove .worktrees/native-coding-reviewed-apply-handoff
git branch -D feat/native-coding-reviewed-apply-handoff
git worktree list --porcelain
git status --short --branch
```

Expected: remote `main` contains the feature commits; temporary worktree and branch are gone.

## Self-Review

- Spec coverage: This plan implements the missing review/apply handoff without replacing `coding_task.execute` or the existing agent loop.
- Placeholder scan: No `TBD`, `TODO`, or unspecified “add tests” steps remain.
- Type consistency: The handle key is consistently `review_handle_id`; the model-facing next call is consistently `coding_task.apply_reviewed_diff`.
