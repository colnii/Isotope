# Isotope Coding Plan v0.1

状态：`archived / historical plan`

归档原因：本文是早期 v0.1 vertical slice（纵向切片）的编码拆解，记录当时的
目录、模块和测试设想；这些设想已经被后续实现、目录重组和 Supervisor 产品路径
替代。当前任务以 `../../current/agent-task-queue.md` 为准，当前架构边界以
`../../architecture/README.md` 和对应 boundary 文档为准。

本文件基于：

- `../../architecture/kernel-spec-v0.1.md`
- `../../architecture/kernel-architecture-v0.1.md`
- `implementation-plan-v0.1.md`

它的目的，是把第一条 v0.1 vertical slice 拆成可执行的 coding plan（编码计划）。它不是最终 package 结构，也不是永久 API 协议。

## 1. Directory Layout

如果第一轮实现仍放在当前 `x-agent` staging repo，必须和现有 assessment pipeline 隔离，使用独立 package namespace：

```text
src/isotope/
  __init__.py
  ids.py
  models.py
  events.py
  refs.py

  event_store.py
  projector.py
  artifact_store.py
  retrieval.py
  memory.py
  workspace.py
  policy.py
  action_compiler.py
  executor.py
  agent_runtime.py
  server.py

  tools/
    __init__.py
    write_artifact.py

tests/isotope/
  test_event_store.py
  test_action_chain.py
  test_policy_grants.py
  test_projector_replay.py
  test_artifact_ref.py
  test_server_slice.py
  test_deferred_capabilities.py
  test_package_isolation.py
```

`src/x_agent/` 不应被第一轮 Isotope slice 修改。`isotope` 不能 import 任何 `x_agent.*` 模块。

## 2. Module Interfaces

### `models.py`

负责 slice-only implementation shapes。

最小对象：

- `Session`
- `Run`
- `AgentInstance`
- `Thread`
- `ActionProposal`
- `PolicyDecision`
- `ActionExecution`
- `Artifact`
- `RunState`

这些可以用 dataclasses 或 Pydantic models，但必须明确只是 implementation shape，不是永久 protocol schema。

### `refs.py`

负责最小 `ResourceRef`。

- 只支持 artifact ref。
- 提供 `make_artifact_ref(run_id, artifact_id) -> ResourceRef`。

### `events.py`

负责 canonical event envelope。

最小字段：

- `event_id`
- `run_id`
- `event_type`
- `payload`
- `created_at`

event names 是 v0 candidate constants，不是永久协议。

### `event_store.py`

负责 file event log。

接口：

- `FileEventStore(root: Path)`
- `append(event: CanonicalEvent) -> CanonicalEvent`
- `list_events(run_id: str) -> list[CanonicalEvent]`
- `event_path(run_id: str) -> Path`

约束：

- 不提供 update API。
- 不提供 delete API。
- append 写入 JSONL。
- 一个 run 一个 event file，例如 `<root>/runs/<run_id>/events.jsonl`。

### `projector.py`

负责 `RunState` projection。

接口：

- `RunProjector`
- `apply(event: CanonicalEvent) -> None`
- `project(events: Iterable[CanonicalEvent]) -> RunState`
- `rebuild(run_id, event_store) -> RunState`

第一版 materialized state 只用 in-memory。Projector 只能消费 canonical events。

### `artifact_store.py`

负责 artifact 写入和 metadata 读取。

接口：

- `ArtifactStore(root: Path)`
- `create_artifact(run_id, execution_id, artifact_type, summary, content) -> Artifact`
- `get_metadata(ref: ResourceRef) -> Artifact metadata / summary`
- `get_content(ref: ResourceRef)`

`get_content()` 可以内部存在，但 projector tests 必须证明 Projector 不依赖 artifact content 推进 native state。

### `retrieval.py`

负责最小 retrieval boundary。

接口：

- `RetrievalService(artifact_store)`
- `get_artifact_summary(ref, grants)`

不实现 ranking、selectors、full content policy 或 budget logic。

### `workspace.py`

负责 workspace binding boundary。

接口：

- `WorkspaceManager`
- `get_binding(grants) -> WorkspaceBinding`

第一版只支持 shared read-only 或 no-op binding。Executor 请求未授权 workspace mode 时必须失败。

### `memory.py`

负责 deferred memory boundary。

接口：

- `NotEnabledMemoryService`
- `query(...)`

第一轮只返回 `not_enabled`，不能写 durable memory，不能进入 action chain。

### `policy.py`

负责最小 policy decision。

接口：

- `PolicyEngine`
- `decide(proposal: ActionProposal) -> PolicyDecision`

必须覆盖：

- `modified`
  - requested 包含 `write_artifact_tool + extra_tool + broad_workspace`
  - grants 只允许 `write_artifact_tool + shared_ro + budget`
- `approved`
  - requested 已经在允许范围内
- `denied`
  - unsupported tool 或 forbidden action

### `action_compiler.py`

负责 compact intent 到 canonical proposal 的编译。

接口：

- `ActionCompiler`
- `compile(intent, runtime_context) -> ActionProposal`

要求：

- malformed intent 必须 rejected。
- policy / execution 前必须先生成 canonical `ActionProposal`。

### `executor.py`

负责执行已授权 action。

接口：

- `Executor`
- `execute(decision, proposal) -> ActionExecution result`

要求：

- 只读取 `decision.grants`。
- 创建 execution lifecycle events。
- 拒绝 unsupported tool。
- 拒绝 ungranted tool。

### `tools/write_artifact.py`

负责 deterministic test tool。

- `WriteArtifactTool`
- 输入固定文本，产出一个 artifact。
- 不暗示最终 tool protocol。

### `agent_runtime.py`

负责 deterministic supervisor loop。

职责：

- 创建 supervisor agent / main thread。
- 将 user input 转成 compact `call_tool` intent。
- 依次调用 Action Compiler、Policy Engine、Executor。
- 根据 projected state 推进 run completion。

### `server.py`

负责 in-process API facade。

第一轮不必实现真实 HTTP。接口：

- `create_session()`
- `create_run(session_id, goal)`
- `submit_input(run_id, text)`
- `get_run_state(run_id)`
- `get_events(run_id)`
- `get_artifact_summary(ref, grants)`

HTTP JSON 可以在 contract tests 通过后再加。第一轮用 in-process facade，避免 transport noise。

## 3. Test Plan

先写 contract tests。

### `test_event_store.py`

- `test_event_store_appends_jsonl_events`
- `test_event_store_has_no_update_or_delete_api`
- `test_event_store_replay_returns_events_in_append_order`
- `test_correction_requires_new_event_not_mutation`

### `test_action_chain.py`

- `test_compact_intent_must_compile_to_action_proposal_before_policy`
- `test_executor_rejects_raw_intent_without_policy_decision`
- `test_proposal_and_decision_are_written_before_execution_started`

### `test_policy_grants.py`

- `test_modified_policy_removes_ungranted_tool_and_workspace`
- `test_executor_uses_grants_not_requested_capabilities`
- `test_unsupported_tool_is_denied_and_not_executed`
- `test_ungranted_workspace_mode_fails`

### `test_artifact_ref.py`

- `test_write_artifact_tool_creates_artifact_with_execution_provenance`
- `test_artifact_has_structured_resource_ref`
- `test_retrieval_summary_uses_resource_ref_not_uri_string`

### `test_projector_replay.py`

- `test_projector_builds_run_state_only_from_events`
- `test_fresh_projector_rebuilds_equivalent_state_from_file_event_log`
- `test_projector_does_not_read_artifact_content_for_native_state`
- `test_run_state_last_event_id_matches_replayed_event_log`

### `test_server_slice.py`

- `test_happy_path_produce_hello_artifact`
- `test_server_run_state_comes_from_projector`
- `test_server_events_come_from_event_store`

### `test_deferred_capabilities.py`

- `test_memory_query_returns_not_enabled`
- `test_external_ingestion_returns_not_enabled`
- `test_checkpoint_returns_not_enabled_or_absent`
- `test_sse_not_exposed_in_slice`

### `test_package_isolation.py`

- `test_isotope_does_not_import_x_agent`

## 4. Implementation Tasks

1. Create isolated `src/isotope/` package and `tests/isotope/` test directory.
2. Add minimal dataclasses / models and ID helpers.
3. Implement `FileEventStore` with JSONL append and replay.
4. Write projector contract tests, then implement minimal `RunProjector`.
5. Implement `ResourceRef` and `ArtifactStore`.
6. Implement deterministic `write_artifact_tool`.
7. Implement `PolicyEngine` with `approved` / `modified` / `denied` cases.
8. Implement `ActionCompiler`.
9. Implement `Executor` enforcing grants only.
10. Implement no-op / shared read-only `WorkspaceManager`.
11. Implement minimal `RetrievalService` for artifact summary by ref and explicit grants.
12. Implement `NotEnabledMemoryService`.
13. Implement deterministic `AgentRuntime`.
14. Implement in-process `Server API` facade.
15. Add end-to-end happy path, modified case, denied / unsupported case.
16. Add deferred capability tests returning `not_enabled`.
17. Add package isolation test proving `isotope` does not import `x_agent.*`.

## 5. File Event Log And Replay

第一版 event log 规则：

- 每个 run 一个 JSONL 文件：`<root>/runs/<run_id>/events.jsonl`。
- `append()` 使用 append mode。
- 每一行写入一个 canonical event。
- Event Store 不暴露 mutation methods。

Replay 验证：

- 删除或丢弃 Projector in-memory state。
- 创建 fresh projector。
- 从 JSONL 读取 events。
- 重建 `RunState`。
- 重建结果必须和原 materialized state 等价。

Projector 只能使用 event payloads。测试中可以对 artifact content read 做 instrumentation：如果 Projector 调用 content read，测试失败。

## 6. Deferred

第一轮 coding 不实现：

- real LLM integration。
- worker spawn 或 multi-agent concurrency。
- real HTTP transport。
- SSE。
- approval pause / resume。
- durable memory 和 controlled expand。
- external ingestion / `ImportedSnapshot`。
- checkpoint。
- isolated workspace substrate。
- SQLite backend。
- full `ResourceRef` selector / version variants。
- retrieval ranking / budget / trimming。
- full `ActionTypeRegistry`。
- domain pack。
- auth、multi-user、quota。
- integration with `src/x_agent`。

## 7. Risks

- In-process Server API 会弱化 transport 覆盖，但 HTTP JSON 是 v0 candidate，不是 hard contract，所以第一轮可以接受。
- File JSONL event log 能证明 append / replay，但不证明 concurrent writes。并发不在第一条 slice。
- Minimal model fields 可能被误读成 protocol。代码注释和文档必须标明它们只是 implementation shape。
- `write_artifact_tool` 可能被误读成 tool protocol。它必须保留为 deterministic test tool，不做泛化。
- Retrieval Service 容易过早扩大。第一轮只做 artifact `ResourceRef` 的 metadata / summary。
- Memory Service 必须保持 `not_enabled`。一旦加入 memory write path，会拉入 deferred contract surface。
- `isotope` 如果 import 任何 `x_agent.*` 模块，就会把 staging slice 和 assessment pipeline 重新耦合，必须用测试挡住。

## 8. Coding Entry Condition

进入编码前需要确认：

- 实现是否继续放在当前 `x-agent` staging repo。
- 如果继续放在本 repo，是否接受新增独立 package `src/isotope/`。
- 第一轮是否只跑 `tests/isotope/`，不触碰现有 `x_agent` assessment pipeline。
