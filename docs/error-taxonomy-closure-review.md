# Error Taxonomy Closure Review

状态：`first slice complete / closed for now`

本文记录 Error Taxonomy first slice 的 closure review。目标是确认当前 slice 是否足以关闭为 v0.2 kernel helper / HTTP facade boundary，同时避免把它误写成 product error UX、public SDK 或完整 error framework。

## Closure Judgment

Error Taxonomy first slice 可以标为 `first slice complete / closed for now`。

当前 slice 已覆盖：

- `src/isotope_kernel/errors.py` 提供最小 `KernelError(ValueError)` compatibility layer。
- `KernelError` 保留 legacy `str(exc)` / `args[0]` message contract。
- Structured attrs 已固定为 `code`、`category`、`retryable`、optional `http_status` 和 low-sensitive `details`。
- First-slice helper paths 覆盖 terminal run、unknown run、unknown session、invalid request 和 `not_enabled`。
- HTTP facade 会优先映射 `KernelError` attrs，同时保留 existing top-level response envelope compatibility。
- `details` validation 拒绝 secret / raw-content / provider-payload style keys。
- Existing stale tests 已同步为 stable `invalid_request` / structured `not_enabled` behavior。

## Evidence

Implementation evidence:

- `src/isotope_kernel/errors.py`
- `src/isotope_kernel/server.py`
- `src/isotope_kernel/http_api.py`
- `tests/isotope_kernel/test_kernel_error_taxonomy_boundary.py`
- `tests/isotope_kernel/test_http_error_mapping_boundary.py`

Verification evidence on the Mac mini checkout:

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/isotope_kernel/test_kernel_error_taxonomy_boundary.py \
  tests/isotope_kernel/test_http_error_mapping_boundary.py \
  -q
# 12 passed

PYTHONPATH=src .venv/bin/python -m pytest \
  tests/isotope_kernel -q \
  --ignore=tests/isotope_kernel/test_packaging_smoke.py
# 1028 passed

export DYLD_LIBRARY_PATH=/opt/homebrew/opt/expat/lib${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope_kernel -q
# 1036 passed
```

Trace demos passed:

- `PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario artifact-review --trace`
- `PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario external-snapshot-review --trace`
- `PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario approval-tool-runner --trace`

## Boundary Confirmations

No overreach was found:

- No product error UX.
- No public SDK error hierarchy.
- No localization / user-facing copy system.
- No real HTTP server.
- No provider / webhook error model.
- No process supervisor / container / git worktree error model.
- No distributed trace system.
- No schema migration framework.
- No external plugin error registry.
- No new dependency.

No kernel semantics were changed outside the intended boundary:

- Event store append-only semantics remain unchanged.
- Projector / replay / checkpoint semantics remain unchanged.
- Executor grants semantics remain unchanged.
- Artifact content read policy remains unchanged.
- HTTP route surface remains in-process facade only.

## Remaining Friction

Remaining friction is intentionally deferred:

- Only first-slice helper / HTTP paths are structured; not every internal `ValueError` has been converted.
- Error code coverage is intentionally narrow: `run_terminal`, `unknown_run`, `unknown_session`, `invalid_request`, and `not_enabled`.
- Product-facing error copy, localization, diagnostics UX, and public SDK typing remain out of scope.
- Future provider / process / workspace-substrate errors should be added only when a concrete kernel slice requires them.

## Next Suggested Path

Default next path: `Application-Layer Friction Intake`.

Specifically, aggressive-dev should consume the mainline `KernelError` behavior and rerun `error.taxonomy.review`. Mainline should only reopen if that produces a new concrete `kernel_friction` with bounded files / tests / repro.

If continuing kernel work explicitly, prefer a review-selected bounded helper / boundary slice. Do not start real HTTP server, real LLM / provider adapter, process supervisor, container, git worktree automation, product error UX, public SDK, tag, or release work from this closure review.
