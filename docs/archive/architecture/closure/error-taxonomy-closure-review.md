# Error Taxonomy Closure Review

状态：`first slice complete / closed for now`

本文记录 Error Taxonomy first slice 的 closure review。目标是确认当前 slice 是否足以关闭为 v0.2 application helper / HTTP facade boundary，同时避免把它误写成 product error UX、public SDK 或完整 error framework。

## Closure Judgment

Error Taxonomy first slice 可以标为 `first slice complete / closed for now`。

当前 slice 已覆盖：

- `src/isotope/platform/errors.py` 提供最小 `IsotopeError(ValueError)` 主类型。
- `src/isotope/errors.py` 和旧 `KernelError` 名称仅保留 compatibility layer。
- `IsotopeError` 保留 legacy `str(exc)` / `args[0]` message contract。
- Structured attrs 已固定为 `code`、`category`、`retryable`、optional `http_status` 和 low-sensitive `details`。
- First-slice helper paths 覆盖 terminal run、unknown run、unknown session、invalid request 和 `not_enabled`。
- HTTP facade 会优先映射 `IsotopeError` attrs，同时保留 existing top-level response envelope compatibility。
- `details` validation 拒绝 secret / raw-content / provider-payload style keys。
- Existing stale tests 已同步为 stable `invalid_request` / structured `not_enabled` behavior。

## Evidence

Implementation evidence:

- `src/isotope/platform/errors.py`
- `src/isotope/errors.py`
- `src/isotope/runtime/in_process.py`
- `src/isotope/interfaces/http.py`
- `tests/isotope/test_isotope_error_taxonomy_boundary.py`
- `tests/isotope/test_http_error_mapping_boundary.py`

Current verification evidence:

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/isotope/test_isotope_error_taxonomy_boundary.py \
  tests/isotope/test_http_error_mapping_boundary.py \
  -q
# 13 passed

PYTHONPATH=src .venv/bin/python -m pytest \
  tests/isotope -q \
  --ignore=tests/isotope/test_packaging_smoke.py
# 1422 passed, 5 skipped

export DYLD_LIBRARY_PATH=/opt/homebrew/opt/expat/lib${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope -q
# 1422 passed, 5 skipped
```

Trace demos passed:

- `PYTHONPATH=src .venv/bin/python -m isotope.demo --scenario artifact-review --trace`
- `PYTHONPATH=src .venv/bin/python -m isotope.demo --scenario external-snapshot-review --trace`
- `PYTHONPATH=src .venv/bin/python -m isotope.demo --scenario approval-tool-runner --trace`

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

No runtime semantics were changed outside the intended boundary:

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
- Future provider / process / workspace-substrate errors should be added only when a concrete application runtime slice requires them.

## Next Suggested Path

Default next path: `Application-Layer Friction Intake`.

Specifically, aggressive-dev should consume the mainline `IsotopeError` behavior and rerun `error.taxonomy.review`. Mainline should only reopen if that produces a new concrete `app_friction` with bounded files / tests / repro.

If continuing platform work explicitly, prefer a review-selected bounded helper / boundary slice. Do not start real HTTP server, real LLM / provider adapter, process supervisor, container, git worktree automation, product error UX, public SDK, tag, or release work from this closure review.
