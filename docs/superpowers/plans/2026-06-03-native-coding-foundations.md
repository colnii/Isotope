# Native Coding Foundations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Isotope's native coding workflow foundations without delegating implementation to Codex CLI.

**Architecture:** Deliver this as a sequence of small, policy-backed capability slices. The first slice registers `coding_task.preview`, a deterministic low-sensitive planning capability that fixes the coding task contract and reports the missing execution substrate before write-capable tools are opened.

**Tech Stack:** Python 3.13, pytest, existing `CapabilityCatalog`, `CapabilityRunner`, action/policy/executor contracts, workspace/artifact/resource-ref boundaries.

---

## Series Roadmap

This objective spans multiple subsystems, so it must not be implemented as one broad patch. Each phase below should become a separate implementation plan or a clearly bounded task group before code changes.

1. `coding_task.preview`: low-sensitive native coding task contract and launch preview.
2. `workspace.isolated_rw`: proposal-only isolated writable workspace contract with path safety.
3. `workspace.lease_create`: event-candidate lease expression for `isolated_rw` without append or materialization.
4. `code.read` / `code.search`: controlled file listing, file read summaries, and code search refs.
5. `code.apply_patch`: structured patch application with path policy, diff artifact, and changed-files artifact.
6. `test.run`: allowlisted validation command runner with stdout/stderr artifacts and stable failure reasons.
7. `vcs.status` / `vcs.diff`: optional Git adapter diagnostics and artifact-backed diff summaries.
8. `coding_task.execute`: bounded agent loop that plans, reads, patches, tests, revises, and reports.
9. Supervisor/Desktop integration: expose native coding capacity in conversation loop and dashboard.

## Slice 1 File Structure

- Create `src/isotope/capabilities/coding.py`: validation and deterministic preview runner for `coding_task.preview`.
- Modify `src/isotope/capabilities/catalog.py`: register `coding_task.preview` in the default catalog.
- Modify `src/isotope/capabilities/runner.py`: route planning and execution through the coding preview runner.
- Modify `tests/unit/capabilities/test_capability_runner_thin_shell.py`: cover discovery, launch plan, successful preview, and fail-closed input validation.

## Slice 2 File Structure

- Create `src/isotope/capabilities/workspace.py`: proposal-only isolated writable workspace contract with path-safety validation.
- Modify `src/isotope/capabilities/catalog.py`: register `workspace.isolated_rw` in the default catalog.
- Modify `src/isotope/capabilities/runner.py`: route planning and execution through the workspace proposal runner.
- Modify `tests/unit/capabilities/test_capability_runner_thin_shell.py`: cover discovery, successful proposal, required-input planning, and unsafe path rejection.

## Slice 3 File Structure

- Modify `src/isotope/capabilities/workspace.py`: add `workspace.lease_create`, which returns a `workspace.lease_created` event candidate and still performs no append, no filesystem write, and no workspace materialization.
- Modify `src/isotope/capabilities/catalog.py`: register `workspace.lease_create` with required provenance ids and `mode="isolated_rw"`.
- Modify `src/isotope/capabilities/runner.py`: route lease-create planning and execution through the workspace runner.
- Modify `src/isotope/platform/state/projector/domain_validation.py`: allow `workspace.lease_created` events to express `isolated_rw` while keeping `workspace.bound` fail-closed to `shared_ro`.
- Modify `src/isotope/platform/state/projector/checkpoint_validation.py`: allow checkpoint-assisted rebuilds to preserve created `isolated_rw` leases.
- Modify `tests/integration/workspace/test_workspace_lease_lifecycle_boundary.py`: cover `isolated_rw` lease projection and checkpoint rebuild.
- Modify `tests/unit/capabilities/test_capability_runner_thin_shell.py`: cover discovery, successful event candidate, and missing-input launch planning.

## Slice 4 File Structure

- Create `src/isotope/capabilities/code_access.py`: controlled `code.read` and `code.search` runners with workspace-relative path validation, bounded excerpts, code refs, and no filesystem writes.
- Modify `src/isotope/capabilities/catalog.py`: register `code.read` and `code.search` in the default catalog with low-sensitive safety boundaries.
- Modify `src/isotope/capabilities/runner.py`: route planning and execution through the code access runner and mark both capabilities `deterministic_readonly`.
- Modify `src/isotope/capabilities/coding.py`: remove `code.read` and `code.search` from the native coding preview blocked-capability list.
- Modify `tests/unit/capabilities/test_capability_runner_thin_shell.py`: cover discovery, bounded read excerpts, bounded search matches, path escape rejection, and missing-input planning.

## Task 1: Register Coding Preview Capability

**Files:**
- Modify: `src/isotope/capabilities/catalog.py`
- Test: `tests/unit/capabilities/test_capability_runner_thin_shell.py`

- [ ] **Step 1: Write failing discovery test**

Add a test that proves the default catalog exposes `coding_task.preview` as a product candidate and advertises the required low-sensitive contract:

```python
def test_runner_discovers_coding_task_preview_from_default_catalog():
    runner = _runner()

    assert "coding_task.preview" in _ids(runner.list_capabilities())
    search = runner.search_capabilities(query="native coding")

    assert "coding_task.preview" in _ids(search["capabilities"])
    description = runner.describe_capability("coding_task.preview")
    assert description["input_contract"]["required"] == ["root", "cwd", "goal"]
    assert description["input_contract"]["properties"]["allowed_paths"]["type"] == "array"
    assert description["input_contract"]["properties"]["verification_commands"]["type"] == "array"
    assert "no_codex_delegation" in description["safety_boundaries"]
    assert "preview_only_no_workspace_write" in description["safety_boundaries"]
```

- [ ] **Step 2: Run test and verify RED**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/capabilities/test_capability_runner_thin_shell.py::test_runner_discovers_coding_task_preview_from_default_catalog -q
```

Expected: fail because `coding_task.preview` is not yet in the default catalog.

- [ ] **Step 3: Add catalog entry**

Add a `Capability(...)` entry to `CapabilityCatalog.default()` with:

- `capability_id="coding_task.preview"`
- `title="Native Coding Task Preview"`
- `domain_tags=("coding", "native", "preview", "workspace", "policy")`
- required inputs `root`, `cwd`, `goal`
- optional array inputs `allowed_paths`, `forbidden_paths`, `verification_commands`
- safety boundaries `no_codex_delegation`, `preview_only_no_workspace_write`, `no_patch_apply`, `no_test_execution`, `low_sensitive_summary_only`

- [ ] **Step 4: Run test and verify GREEN**

Run the same focused test. Expected: pass.

## Task 2: Implement Deterministic Preview Runner

**Files:**
- Create: `src/isotope/capabilities/coding.py`
- Modify: `src/isotope/capabilities/runner.py`
- Test: `tests/unit/capabilities/test_capability_runner_thin_shell.py`

- [ ] **Step 1: Write failing run test**

Add a test that proves the preview returns the coding contract without writing files or invoking Codex:

```python
def test_runner_runs_coding_task_preview_without_side_effects(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    root = tmp_path / "state"

    result = _runner().run_capability(
        "coding_task.preview",
        inputs={
            "root": str(root),
            "cwd": str(workspace),
            "goal": "Add a native code edit action.",
            "allowed_paths": ["src/isotope/capabilities"],
            "verification_commands": ["pytest tests/unit/capabilities -q"],
        },
    )

    assert result["kind"] == "capability_run_result"
    assert result["capability_id"] == "coding_task.preview"
    assert result["status"] == "completed"
    assert result["runner_kind"] == "deterministic_preview"
    assert result["preview"]["goal"] == "Add a native code edit action."
    assert result["preview"]["cwd_status"] == "exists"
    assert result["preview"]["execution_mode"] == "preview_only"
    assert result["preview"]["native_coding_requirements"] == [
        "policy_granted_writable_workspace",
        "controlled_code_read_search",
        "structured_patch_application",
        "allowlisted_test_execution",
        "artifact_backed_diff_and_changed_files",
        "optional_vcs_adapter",
    ]
    assert result["preview"]["blocked_capabilities"] == [
        "workspace.isolated_rw",
        "code.read",
        "code.search",
        "code.apply_patch",
        "test.run",
        "vcs.status",
        "vcs.diff",
    ]
    assert not list(root.rglob("*"))
```

- [ ] **Step 2: Run test and verify RED**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/capabilities/test_capability_runner_thin_shell.py::test_runner_runs_coding_task_preview_without_side_effects -q
```

Expected: fail because the runner does not route `coding_task.preview`.

- [ ] **Step 3: Create `coding.py`**

Implement:

- `CODING_TASK_PREVIEW_CAPABILITY = "coding_task.preview"`
- `is_coding_capability(capability_id: str) -> bool`
- `validate_coding_inputs(...)`
- `run_coding_task_preview(...)`

The runner must:

- require `root`, `cwd`, and non-empty `goal`
- accept list-of-string `allowed_paths`, `forbidden_paths`, and `verification_commands`
- return only low-sensitive strings, counts, and capability ids
- not create directories, write artifacts, run tests, call providers, or call Codex

- [ ] **Step 4: Wire `runner.py`**

Import coding helpers, include coding validation in `plan_capability_run(...)` and `run_capability(...)`, update `_runner_kind(...)`, and dispatch `CODING_TASK_PREVIEW_CAPABILITY` to `run_coding_task_preview(...)`.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/capabilities/test_capability_runner_thin_shell.py -q
```

Expected: all tests in the file pass.

## Task 3: Validate Fail-Closed Input Contract

**Files:**
- Modify: `tests/unit/capabilities/test_capability_runner_thin_shell.py`
- Modify: `src/isotope/capabilities/coding.py`

- [ ] **Step 1: Write failing validation tests**

Add tests for malformed list inputs and missing cwd:

```python
def test_coding_task_preview_rejects_malformed_path_lists(tmp_path):
    with pytest.raises(ValueError, match="allowed_paths"):
        _runner().run_capability(
            "coding_task.preview",
            inputs={
                "root": str(tmp_path / "state"),
                "cwd": str(tmp_path),
                "goal": "Edit code.",
                "allowed_paths": "src",
            },
        )


def test_coding_task_preview_reports_missing_cwd_without_creating_it(tmp_path):
    missing = tmp_path / "missing"

    result = _runner().run_capability(
        "coding_task.preview",
        inputs={
            "root": str(tmp_path / "state"),
            "cwd": str(missing),
            "goal": "Edit code.",
        },
    )

    assert result["preview"]["cwd_status"] == "missing"
    assert not missing.exists()
```

- [ ] **Step 2: Run tests and verify RED or partial RED**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/capabilities/test_capability_runner_thin_shell.py::test_coding_task_preview_rejects_malformed_path_lists tests/unit/capabilities/test_capability_runner_thin_shell.py::test_coding_task_preview_reports_missing_cwd_without_creating_it -q
```

Expected: fail until validation and missing-cwd reporting are implemented.

- [ ] **Step 3: Implement validation and missing-cwd status**

Make `validate_coding_inputs(...)` reject non-list or non-string list entries for array fields. Make `run_coding_task_preview(...)` return `cwd_status` as `exists` or `missing` without creating the path.

- [ ] **Step 4: Run full targeted verification**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/capabilities/test_capability_runner_thin_shell.py tests/unit/capabilities/test_capability_catalog_core.py -q
git diff --check
```

Expected: tests pass and diff check reports no whitespace errors.

## Task 4: Commit Slice 1

**Files:**
- Stage only files changed by this slice.

- [ ] **Step 1: Inspect diff**

Run:

```bash
git diff -- src/isotope/capabilities/coding.py src/isotope/capabilities/catalog.py src/isotope/capabilities/runner.py tests/unit/capabilities/test_capability_runner_thin_shell.py docs/superpowers/plans/2026-06-03-native-coding-foundations.md
```

- [ ] **Step 2: Stage related files**

Run:

```bash
git add src/isotope/capabilities/coding.py src/isotope/capabilities/catalog.py src/isotope/capabilities/runner.py tests/unit/capabilities/test_capability_runner_thin_shell.py docs/superpowers/plans/2026-06-03-native-coding-foundations.md
```

- [ ] **Step 3: Commit**

Run:

```bash
git commit -m "feat(capabilities): add native coding preview contract"
```

## Self-Review

- Spec coverage: this plan covers only Slice 1 in implementation detail and preserves the broader series roadmap for later plans.
- Placeholder scan: no implementation step depends on a TBD value.
- Type consistency: `coding_task.preview`, `root`, `cwd`, `goal`, `allowed_paths`, `forbidden_paths`, and `verification_commands` are used consistently across tests, catalog, and runner.

## Slice 2: Isolated Writable Workspace Proposal

**Goal:** Register `workspace.isolated_rw` as the next native-coding substrate contract without claiming real workspace materialization.

**Current implementation boundary:**

- `workspace.isolated_rw` returns a deterministic `workspace_proposal`.
- It validates `root`, `cwd`, `workspace_name`, `allowed_paths`, and `forbidden_paths`.
- It rejects absolute paths, parent traversal, empty relative paths, and non-list path fields.
- It does not create directories, create git worktrees, copy files, append events, or mutate workspace state.
- It reports the next required capabilities: `workspace.lease_create`, `workspace.materialize`, `workspace.changed_files`, and `workspace.release`.
