# Error Taxonomy Boundary v0.2

状态：`first slice complete / closed for now`

## 1. Purpose

本文定义 Isotope kernel error taxonomy（错误分类）的最小 contract。目标是解决 application-layer pressure 暴露的 `unstructured_kernel_helper_errors`：HTTP facade 已返回 stable `status` / `error.code` / `error.message` envelope，但 direct in-process helpers 仍主要抛 plain `ValueError(...)`，app shell 要区分 terminal conflict、validation、unknown id、not-enabled 等错误时只能 parse message string。

本边界只定义 kernel-level error shape，不实现 product error UX、public SDK、real HTTP server、provider adapter、process supervisor、container、git worktree、tag 或 release。

## 2. Current Friction

Aggressive-dev `error.taxonomy.review` 证明：

- HTTP facade errors already expose structured response envelope.
- `InProcessServer.submit_input(...)` on terminal run currently raises `ValueError("run is terminal: completed")`.
- App shell cannot reliably classify helper errors without string matching.
- The same issue can appear for unknown session / run, invalid request, disabled capability / `not_enabled`, and policy / lifecycle conflicts.

This is kernel-level because helper errors are part of the in-process kernel surface consumed by demos, app spikes, capability hub, and future application shells.

## 3. Definitions

- `KernelError`: kernel-owned structured exception for controlled helper / facade failures.
- `code`: stable snake_case identifier such as `run_terminal` or `unknown_run`; never include dynamic ids.
- `category`: small stable class used for routing and policy, not prose.
- `retryable`: boolean hint for callers; it is not a retry scheduler.
- `http_status`: optional HTTP-style status mapping for facades; it does not imply a real HTTP server.
- `details`: low-sensitive structured metadata such as `run_id`, `session_id`, `status`, or `field`.
- `message`: legacy human-readable string preserved through `str(exc)` and `args[0]`.

## 4. Hard Contracts

- `KernelError` should subclass `ValueError` so existing `pytest.raises(ValueError)` and caller compatibility remain intact.
- `str(exc)` and `exc.args[0]` must preserve the old readable message contract.
- `code` must be stable snake_case and must not contain dynamic ids.
- `category` must come from a small allowlist.
- `retryable` must be explicit.
- `http_status` is optional metadata for facade mapping, not a network server contract.
- `details` must not contain artifact full content, raw provider payload, secrets, binary content, or user-private raw content.
- HTTP facade should map from structured attrs first and keep existing response envelope compatibility.
- Direct helpers should not require callers to parse message strings for ordinary controlled kernel failures.
- Error taxonomy must not mutate event log, projector state, checkpoint state, executor grants, policy decisions, or artifact content behavior.

## 5. Minimal v0.2 Shape

Candidate `KernelError` fields:

| Field | Type | Contract |
| --- | --- | --- |
| `code` | `str` | stable snake_case identifier |
| `category` | `str` | one of the allowlisted categories |
| `retryable` | `bool` | explicit caller hint |
| `http_status` | `int | None` | optional facade mapping |
| `details` | `dict` | low-sensitive structured metadata |
| message | `str` | legacy `ValueError` message |

Initial `code` candidates:

- `run_terminal`
- `unknown_run`
- `unknown_session`
- `invalid_request`
- `not_enabled`

Initial `category` allowlist:

- `validation`
- `not_found`
- `conflict`
- `not_enabled`
- `policy`
- `lifecycle`
- `internal`

## 6. HTTP Facade Mapping

HTTP facade should prefer structured error attrs when present:

- `error.code` should come from `KernelError.code`.
- `error.message` should remain the readable message.
- `status_code` should use `http_status` when set.
- existing top-level `status` and nested `error.code` / `error.message` shape should remain backward-compatible.

If a non-`KernelError` escapes a controlled boundary, the facade may still wrap it conservatively, but new kernel helper paths should use structured errors for expected failures.

## 7. First Slice Scope

First green slice should cover only:

- terminal run ordinary input rejection: `run_terminal` / `conflict` or `lifecycle`.
- unknown run: `unknown_run` / `not_found`.
- unknown session: `unknown_session` / `not_found`.
- invalid request / malformed input: `invalid_request` / `validation`.
- disabled capability / deferred path: `not_enabled` / `not_enabled`.

Keep existing messages compatible. Do not redesign all exception paths at once.

## 8. Deferred

- product error UX
- public SDK error hierarchy
- localization / user-facing copy system
- real HTTP server
- provider adapter / webhook error model
- process supervisor / container / git worktree errors
- distributed trace ids
- schema migration framework
- external plugin error registry

## 9. First Red Tests Recommendation

Suggested tests:

- `tests/isotope_kernel/test_kernel_error_taxonomy_boundary.py`
- `tests/isotope_kernel/test_http_error_mapping_boundary.py`

Initial coverage:

1. `KernelError` exists and subclasses `ValueError`.
2. `KernelError` preserves `str(exc)` / `args[0]`.
3. errors expose `code`, `category`, `retryable`, `http_status`, and `details`.
4. terminal run `submit_input(...)` raises `KernelError` with stable `run_terminal` metadata.
5. unknown run / session and invalid input paths expose stable metadata.
6. `not_enabled` helper / HTTP paths expose stable metadata.
7. HTTP envelope remains backward-compatible.
8. details reject or avoid raw content / secrets.
9. no real HTTP server, product SDK, provider, process, container, git worktree, tag, or release.

## 10. Implementation Status

First slice 已实现并完成 closure review，见 `error-taxonomy-closure-review.md`。

当前实现包括：

- `KernelError(ValueError)` compatibility layer。
- Legacy `str(exc)` / `args[0]` message compatibility。
- Stable `code` / `category` / `retryable` / `http_status` / `details` attrs。
- terminal run、unknown run/session、invalid request 和 `not_enabled` helper / HTTP mapping first paths。
- low-sensitive `details` validation。

仍 deferred：product error UX、public SDK、real HTTP server、provider / process / container / git-worktree error model、plugin error registry、tag 和 release。

## 11. Decision

Error Taxonomy Boundary is accepted as a completed first slice. Future expansion should be driven by concrete application-layer `kernel_friction`, not by broad conversion of all exceptions.
