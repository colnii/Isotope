# Native Coding Reviewed Apply Design

Date: 2026-06-04

## Goal

Let a user explicitly apply a verified native-coding isolated workspace back to
the source workspace after review.

## Scope

Add a product capability:

```text
coding_task.apply_reviewed_diff
```

It applies the changed files from `root/workspaces/<workspace_id>` back into
`cwd` only after the user/model calls the capability. It does not commit, push,
merge, or release the workspace.

## Contract

Required inputs:

- `root`: system runtime state root.
- `cwd`: system source workspace.
- `workspace_id`: reviewed isolated workspace id.

Optional inputs:

- `include_paths`: workspace-relative paths to apply, default `["."]`.
- `expected_changed_files`: expected changed file paths from the review result.

Output:

- `status`: `applied` or `blocked`.
- `workspace_id`.
- `changed_files`.
- `applied_files`.
- `blocked_reason`.
- `source_workspace_write`: `performed` only on success.

## Safety

- Only paths under `cwd` and `root/workspaces/<workspace_id>` may be touched.
- Symlinks are not followed.
- Source files must still match the original source snapshot implied by the
  reviewed workspace comparison. If the source changed since review, block.
- Deletions are blocked for this first slice.
- Raw file content and raw patch text do not appear in summaries.

## Architecture

Reuse existing filesystem boundaries from `workspace_files.py` and path safety
from native coding capabilities. Add a small deterministic capability runner
under `src/isotope/capabilities/` and wire it through `CapabilityRunner` and the
catalog. Supervisor can call it through the existing capability path; no new
agent loop is introduced.

## Tests

Target tests should prove:

- Capability appears in the default catalog.
- Applying a changed reviewed workspace updates source files.
- Source conflict blocks without partial writes.
- Missing materialized workspace blocks.
- Deleted files are blocked in this first slice.
- Result summaries do not expose raw file content.
