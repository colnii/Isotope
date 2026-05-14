# Agent / Worker Lifecycle Boundary v0.2

状态：`first slice complete`

## 1. Purpose

Agent / Worker lifecycle 是 Kernel Gap Review v0.2 后的最高优先级 kernel design。它不是为了立刻实现多 agent、real LLM loop 或并发执行，而是先定义 supervisor、worker、delegation 和 worker handoff 的 hard boundary，避免后续 usability pressure test 时把 worker 当成普通函数调用。

这块设计优先于 real HTTP server、memory query、provider adapter 和 domain pack，因为 worker lifecycle 会影响：

- delegation 是否必须经过 policy。
- workspace binding 如何授予和隔离。
- approval、retry、cancel、supersede 如何作用到 worker 和 action lifecycle。
- session continuity 如何表达 worker result，而不直接突变 session state。
- projector / checkpoint 如何从 canonical events 重建 worker read model。

## 2. Current Capabilities

当前 kernel 已有这些可复用能力：

- supervisor instance：v0.1 / v0.2 demo 中已有 deterministic supervisor path。
- deterministic `AgentRuntime` boundary：当前仍是很薄的 runtime placeholder，足以表明 agent runtime 是 kernel 层关注点。
- `ActionCompiler -> PolicyEngine -> Executor` action chain。
- `PolicyDecision.grants` enforcement。
- canonical event log。
- `RunProjector` / `RunState` replay 和 checkpoint-assisted rebuild。
- minimal thread / agent concepts in design docs。
- approval boundary：pending / approved / denied / duplicate conflict 已可 event-source 和 checkpoint。
- workspace boundary：当前只有 `shared_ro` grants binding。

这些能力证明 kernel 可以约束 execution。当前 first slice 已把 supervisor / worker / delegation read model 接入 `RunProjector`，但仍不是 real multi-agent runtime。

## 3. Current Gaps

当前缺口：

- worker spawn 只有 slice-only canonical event / read model，不是真实 spawn。
- worker state machine 只有 first-slice statuses：`created` / `running` / `completed` / `failed` / `cancelled`。
- delegation proposal / policy decision 已有 projector-level boundary，但还没有 product-level delegation API。
- worker promotion / persistence 未定义。
- worker workspace binding 仍只有 shared read-only boundary。
- worker failure / cancellation 已有 first-slice status；supersede 未定义。
- worker result handoff 已有 artifact / `ResourceRef` / event boundary；更复杂 handoff 未定义。
- multi-worker concurrency 未定义。
- worker read model 已进入 `RunState.workers`；agent read model 已进入 `RunState.agents`。

这些缺口不应通过直接实现 real LLM / process spawn 来补。先定义 boundary，再进入 red tests。

## 4. Hard Boundaries

- Worker 是 kernel concept，不只是 Python function call。
- Model 可以 propose delegation，但 runtime policy 决定是否允许。
- Worker creation 必须来自 canonical delegation proposal + policy decision。
- Worker 不能绕过 `ActionCompiler` / `PolicyEngine` / `Executor` / event log。
- Worker lifecycle state 必须 event-sourced，并可 replay / checkpoint-assisted rebuild。
- Workspace binding 是 granted execution resource，不是 agent identity。
- Worker 不能直接 mutate `SessionState` / `RunState` / memory / artifact read model。
- Worker result handoff 必须通过 artifact / `ResourceRef` / canonical event，而不是 in-memory object handoff。
- Worker approval、failure、cancel、supersede 必须进入 canonical event log。
- First slice 不实现 real concurrency、process isolation 或 remote worker。

## 5. Proposed Minimal Lifecycle

v0.2 / v0.3 minimal target 只定义 lifecycle shape，不承诺完整 implementation。

### 5.1 AgentInstance Read Model

First green slice 中，`AgentInstance` read model 已由 `RunProjector` 从 canonical events 投影到 `RunState.agents`。当前至少表达：

- `agent_id`
- `run_id`
- `role`: `supervisor` or `worker`
- `status`: `created`, `running`, `completed`, `failed`, `cancelled`
- `parent_agent_id`
- `delegation_id`
- `created_event_id`
- `last_event_id`

该 read model 只由 projector 从 canonical events 派生。

`Worker` read model 已由 `RunProjector` 投影到 `RunState.workers`，包含：

- `worker_id`
- `agent_id`
- `parent_agent_id`
- `delegation_id`
- `decision_id`
- `status`
- `requested_capabilities`
- `grants`
- `workspace`
- `result_refs`
- `created_event_id`
- `last_event_id`

`RunProjector.create_checkpoint(...)` 的 checkpoint state 现在包含 `agents` / `workers`，与 `approvals` / `memory_records` / `external_observations` 一样作为 read-model projection 保存；checkpoint-assisted rebuild 可以恢复同等 agent / worker read model。

### 5.2 Worker Lifecycle Events

第一批 boundary 已使用这些 slice-only canonical events：

- `agent.created`
- `delegation.proposed`
- `delegation.decided`
- `worker.created`
- `worker.started`
- `worker.completed`
- `worker.failed`
- `worker.cancelled`
- `worker.result_handed_off`

这些事件名是 v0.2 boundary proposal，不是永久协议。

### 5.3 Delegation Action Boundary

Delegation 应作为 action-like boundary：

1. Supervisor 产生 delegation intent。
2. `ActionCompiler` 或 equivalent compiler 生成 canonical delegation proposal。
3. `PolicyEngine` 决定 delegation 是否允许，并缩减 tools / workspace / budget。
4. Denied delegation 不创建 worker。
5. Approved delegation append canonical event，然后创建 worker read model。
6. Worker 后续 action 仍必须走 action chain 和 grants enforcement。

### 5.4 Workspace Binding

Worker workspace binding 只来自 policy grants：

- worker request 不能直接决定 workspace mode。
- executor / worker runtime 只能使用 decision grants。
- workspace binding summary 可进入 worker read model。
- workspace binding 不等于 agent identity。

当前 first slice 可以继续只支持 `shared_ro`，但必须保留未来 isolated workspace 的 contract slot。

### 5.5 Result Handoff

Worker result 不能直接写 native run state。允许的 handoff 形态：

- artifact created with provenance
- structured `ResourceRef`
- canonical event referencing artifact / worker / delegation
- read model projection from event log

禁止：

- direct Python object mutation
- direct `RunState` mutation
- direct session memory promotion
- untracked workspace file becoming state

## 6. Deferred

本阶段不做：

- real parallel execution
- long-lived worker persistence
- remote worker
- process / container isolation
- scheduling / load balancing
- real LLM planning loop
- worker promotion across sessions
- multi-user worker ownership
- worker auth / identity
- production queue / job runner

## 7. Implemented First Slice

第一批 red tests 已落地并 green，当前可标为 first slice complete：

- `tests/isotope/test_agent_worker_lifecycle_boundary.py`
- `tests/isotope/test_delegation_policy_boundary.py`

当前覆盖：

- supervisor exists as first-class agent instance。
- worker spawn requires canonical delegation proposal。
- delegation proposal must pass policy before worker is created。
- denied delegation creates no worker。
- approved delegation creates worker via canonical event。
- worker state is projected from events。
- replay restores worker read model。
- checkpoint-assisted rebuild restores worker read model。
- worker cannot execute action without policy grants。
- worker workspace binding comes from grants。
- worker result handoff uses artifact / ref / event, not direct state mutation。
- no real concurrency / process spawn in first slice。

同时最小同步了既有 checkpoint creation expected fields：`agents` / `workers` 与 `approvals`、`memory_records`、`external_observations` 一样属于 checkpointed `RunState` read model。

## 8. Acceptance For This Boundary

该 boundary 当前可以被视为 first slice complete：

- worker lifecycle 不再只是 `agent_runtime.py` placeholder。
- delegation / worker creation 的 policy path 明确。
- worker read model 的 projected shape 明确。
- workspace binding、result handoff、approval / failure / cancel interactions 有 first-slice stance。
- deferred list 明确，避免被误解成 multi-agent product。

下一步不是 real concurrency，而是 Workspace substrate boundary design。
