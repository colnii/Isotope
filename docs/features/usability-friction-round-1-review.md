# Usability Friction Round 1 Review

状态：`closed; first round complete`

## 1. Purpose

本文收口 `approval-tool-runner` usability pressure test 暴露的第一轮 developer ergonomics friction（开发者易用性摩擦）。

本轮不是继续扩大 spike，也不是把 spike 变成 product API。目标是判断当前 helper slices 是否已经足够，让后续不再围绕同一个 demo 无限打磨。

当前 evidence：

- baseline: `865 passed`
- `python -m isotope.demo --scenario approval-tool-runner`
- `python -m isotope.demo --scenario approval-tool-runner --json`
- `approval-tool-runner` remains deterministic / in-process
- no real HTTP server / real LLM / provider adapter / filesystem mutation

## 2. Friction Removed

### Approval id lookup

Removed friction:

- demo no longer scans canonical events to find `approval_id`
- caller can use `InProcessServer.get_pending_approvals(run_id)`
- caller can use `InProcessServer.get_approval(run_id, approval_id)`
- in-process HTTP read helper routes exist for approval lookup

Layer:

- read-model helper / facade issue
- not a kernel correctness issue

### Workspace binding glue

Removed friction:

- demo no longer hand-writes `workspace.bound` payload
- caller can use `InProcessServer.bind_workspace(run_id, decision, bound_to=None)`
- helper derives binding from `PolicyDecision.grants`
- helper appends canonical `workspace.bound`
- helper returns projected `RunState.workspaces` summary

Layer:

- server helper / workspace ownership issue
- not real filesystem substrate

### Approval-gated submission helper

Removed friction:

- demo no longer directly calls raw `submit_tool_request(...)`
- caller can use `InProcessServer.submit_action(run_id, intent, requires_approval=True)`
- helper accepts compact `call_tool` intent
- helper returns proposal / decision / approval / execution ids as applicable
- existing `submit_tool_request(...)` remains compatible

Layer:

- server facade/helper issue
- not a new action engine
- not a product API

## 3. Friction Remaining

Remaining friction is now narrower:

- `POST /runs/{run_id}/input` still has no approval-gated option.
- HTTP approval-gated submission shape remains undefined.
- `approval-tool-runner` still demonstrates a kernel helper path, not a product-level tool runner.
- The demo still depends on deterministic `write_artifact_tool`; it is not a real tool protocol.

This remaining friction is mostly app / facade-level:

- HTTP facade shape question: whether approval-gated submission belongs on `/input`, a new action route, or not in HTTP yet.
- App helper question: future tiny app scenarios may want a small scenario runner helper, but not a product API.

It is not currently a kernel-level blocker:

- canonical action proposal path exists.
- policy / grants boundary exists.
- pending approval does not execute.
- approved path resumes through executor.
- workspace binding is event-sourced.
- artifact handoff uses `ResourceRef`.
- replay and checkpoint are covered.

## 4. Is Approval Tool Runner Reasonable Now?

Yes, as a developer demo / pressure test.

It now demonstrates:

- in-process HTTP facade for session / run / state / events
- approval pause / resume
- approval lookup helper
- compact submit action helper
- workspace binding helper
- artifact / `ResourceRef` handoff
- replay
- checkpoint-assisted rebuild
- explicit non-goals in JSON status

It should not be presented as:

- product tool runner
- real filesystem runner
- hosted HTTP API
- real LLM loop
- process executor
- approval UI

## 5. Closure Judgment

Round 1 friction reduction is complete enough.

Do not keep expanding `approval-tool-runner` by default. The spike has already served its purpose:

- it exposed raw event-scan glue
- it exposed manual workspace binding glue
- it exposed raw tool submission helper glue
- all three have bounded helper slices now

The next useful signal should come from a different app-shaped pressure test, not another incremental polish round on the same spike.

## 6. Suggested Next Direction

Next recommended app-shaped spike: `artifact review flow`.

Reason:

- it exercises artifact summary and controlled content retrieval policy
- it uses `ResourceRef` and provenance
- it can stay deterministic and in-process
- it does not need real filesystem mutation
- it does not need real LLM
- it can use the existing HTTP facade without opening a real server
- it is less likely than research assistant / file summarizer to overclaim product readiness

Next batch should be red-tests-only:

- define expected CLI / in-process scenario behavior
- define JSON summary shape
- verify no full content leaks by default
- verify explicit controlled content retrieval path
- verify no real filesystem / network / model usage
- do not implement until the red tests are reviewed or the queue explicitly allows green
