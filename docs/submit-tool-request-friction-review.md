# Submit Tool Request Friction Review

状态：`current; helper recommended`

## 1. Purpose

本文 review `approval-tool-runner` spike 暴露的 remaining API friction：approval-gated input 仍需要直接调用 `InProcessServer.submit_tool_request(...)`。

本轮目标不是产品化 tool runner，也不是打开 HTTP product API。目标是判断这个 friction 属于 kernel design issue、server facade/helper gap、demo glue，还是可接受的 v0 shape。

当前 evidence：

- `python -m isotope_kernel.demo --scenario approval-tool-runner`
- `python -m isotope_kernel.demo --scenario approval-tool-runner --json`
- full regression after workspace binding helper slice: `859 passed`
- approval lookup/read helper 已移除 event-scan approval id glue
- workspace binding helper 已移除 manual `workspace.bound` glue

## 2. Finding

`submit_tool_request(...)` 本身不是 correctness bug。它已经走：

- compact intent -> canonical `ActionProposal`
- `PolicyEngine.decide(...)`
- `PolicyDecision.grants`
- pending approval boundary
- executor path
- artifact / `ResourceRef` handoff
- event replay / checkpoint read model

friction 在于命名和返回形状太接近 internal tool request：

- demo 想表达的是 “submit an action that may require approval”，不是 “directly submit a tool request”。
- helper caller 需要知道 `tool` / `text` / `requires_approval` 这组低层参数。
- helper result 对 approval path 缺少一眼可读的 `proposal_id` / `decision_id` / `approval_id` summary。
- `approval-tool-runner` JSON 仍记录 `submit_tool_request(...)`，使外部读者容易误解当前推荐 API 就是 raw tool helper。

## 3. Classification

| Friction | Classification | Kernel impact | Suggested action |
| --- | --- | --- | --- |
| `submit_tool_request(...)` naming exposes tool-specific surface | server facade/helper gap | low | add narrow `submit_action(...)` helper |
| approval-gated submission needs explicit `requires_approval=True` | server facade/helper gap | low-medium | keep explicit flag for now; do not infer approval |
| result lacks compact id summary | helper shape gap | low | return proposal / decision / approval / execution ids |
| direct HTTP `/runs/{run_id}/input` has no approval flag | deferred HTTP facade question | medium | defer; do not productize HTTP route in this slice |

## 4. Layer Decision

Kernel layer:

- No kernel contract rewrite is required.
- The existing action chain, policy decision, approval boundary, executor ownership, event log, and projector remain the source of truth.
- The helper must not create an action, approval, execution, or artifact outside canonical events.

Server facade/helper layer:

- Add a small `InProcessServer.submit_action(...)` helper.
- Accept compact user/tool intent and compile it with `ActionCompiler`.
- Return a useful in-process summary with canonical ids and status.
- Preserve `submit_tool_request(...)` as a compatibility helper.

Demo glue layer:

- `approval-tool-runner` should call `submit_action(...)` instead of `submit_tool_request(...)`.
- It should continue using approval lookup/read helper for approval id discovery.
- It should continue using `bind_workspace(...)` for workspace binding.

Acceptable v0 shape:

- `submit_tool_request(...)` can remain public and compatible because existing tests and callers use it.
- `submit_action(...)` is an in-process helper, not a product API.
- Returning an internal `PolicyDecision` object for same-process helper composition is acceptable only if the summary also exposes stable ids; no external JSON output should expose Python object repr.

## 5. Recommended Helper Boundary

Preferred shape:

```python
InProcessServer.submit_action(
    run_id,
    {
        "action": "call_tool",
        "tool": "write_artifact_tool",
        "text": "...",
    },
    requires_approval=True,
)
```

Minimum contract:

- validates known `run_id`
- validates compact action intent
- compiles to canonical `ActionProposal`
- appends `action.proposed`
- runs policy
- uses `PolicyDecision.grants`, not requested capabilities
- appends `action.decided`
- if `requires_approval=True`, returns pending approval summary and does not execute
- if approved / modified, executes through existing `Executor`
- if denied, does not execute or create artifact
- returns useful ids:
  - `proposal_id`
  - `decision_id`
  - `approval_id` when pending
  - `execution_id` when execution starts
  - `artifact_ref` when artifact is produced

## 6. Non-Goals

Do not implement in this slice:

- real HTTP server
- HTTP approval-gated input product route
- approval UI / auth / notification / scheduler
- real tool runner
- real filesystem mutation
- process spawn / container / git worktree
- provider adapter
- memory query engine
- automatic action retry / cancellation

## 7. First Red Tests

Recommended test file:

- `tests/isotope_kernel/test_submit_action_helper.py`

Test goals:

- helper accepts compact user/tool intent
- helper produces canonical action proposal path
- helper respects approval requirement
- helper returns useful summary including proposal / decision / approval / execution ids as applicable
- helper does not execute pending approval action
- helper uses grants, not requested capabilities
- helper does not create artifact when pending / denied
- existing `submit_tool_request(...)` behavior remains compatible
- `approval-tool-runner` demo no longer calls raw `submit_tool_request(...)`

## 8. Recommendation

Proceed with a narrow `submit_action(...)` first slice.

Rationale:

- It directly addresses the only remaining visible friction in the current spike.
- It does not require changing kernel contracts.
- It keeps the HTTP facade deferred.
- It reduces demo glue without hiding approval, workspace, artifact, replay, or checkpoint boundaries.
