# Terminal Backend Adapter Contract v0.2

状态：`historical compatibility doc / fake runner contract implemented`

Terminology correction: this file name and the `TerminalBackend*` code names are historical compatibility names. The current source of truth is [Terminal Capacity / System Runner Boundary v0.2](./terminal-capacity-system-runner-boundary-v0.2.md). Read "backend" here as terminal capacity runner / execution substrate. `terminal` is a capacity, system terminal is the runner, and Codex is reference code / optional code-writing tool work rather than Isotope's terminal backend.

本文把 [Real Terminal Backend Boundary](./real-terminal-backend-boundary-v0.2.md) 进一步拆成可测试的 compatibility contract。它回答一个问题：Isotope 如果接系统终端 runner，双方应该怎么交接，哪些数据能过边界，哪些必须被挡住。

本 slice 不选择具体 runner，不接 Codex / opencode / Claude，不引入 dependency，不开放新命令。当前实现提供 Python 合同对象、fake runner adapter，以及 `Executor` / `InProcessServer` 的可配置 fake runner 接线路径，用来验证边界规则。

## Implementation Status

当前 green slices 包含：

- `src/isotope_kernel/terminal_backend.py`
- `TerminalBackendRequest`
- `TerminalBackendResult`
- `TerminalBackendOutputArtifact`
- `TerminalBackendRunResult`
- `TerminalBackendFailure`
- `TerminalBackendCancelResult`
- `TerminalBackendAdapter`
- `TerminalBackendConfig`
- `build_terminal_backend_request(...)`
- `TerminalBackendProtocolError`
- `TerminalBackendExecutionError`
- `TerminalBackendNotConfiguredError`
- `Executor(..., terminal_backend=...)`
- `Executor(..., terminal_backend_config=...)`
- `InProcessServer(..., terminal_backend=...)`
- `InProcessServer(..., terminal_backend_config=...)`

当前测试入口：

- `tests/isotope_kernel/test_terminal_backend_adapter_contract.py`
- `tests/isotope_kernel/test_terminal_backend_executor_integration.py`
- `tests/isotope_kernel/test_terminal_backend_selector_config.py`
- `tests/isotope_kernel/test_terminal_backend_artifact_policy.py`

已验证的范围：

- approved / modified `PolicyDecision` 才能构造 backend request。
- denied decision 不会调用 backend。
- pending approval 不会调用 backend。
- request 使用 `PolicyDecision.grants` snapshot，后续外部 mutation 不会影响 request。
- backend output artifact content 进入 artifact store，再变成 structured `ResourceRef`。
- safe summary / adapter result 不包含完整 stdout / stderr content。
- backend 上报 forged grants 会被拒绝。
- backend 上报 raw file path artifact ref 会被拒绝。
- unknown backend status fail closed with structured `TerminalBackendProtocolError`。
- `TerminalBackendFailure` 使用 stable reason code、message、retryable 和 low-sensitive details。
- cancel path 会转发给 backend，并保留 basis event linkage。
- 配置了 `terminal_backend` 时，`Executor` 会通过 `TerminalBackendAdapter` 构造 request，不再直接调用本地 `ControlledTerminalRunner`。
- fake backend 输出只通过 artifact store / structured `ResourceRef` 进入事件链；event payload 不包含完整输出。
- backend 上报失败会变成 structured `action.failed`，不会追加 `artifact.created` / `action.completed`。
- backend 说 completed 但没有 output artifact 会 fail closed。
- `InProcessServer(..., terminal_backend=...)` 可把 `submit_action(... terminal_exec ...)` 路由到配置的 fake backend。
- `TerminalBackendConfig` 会进入 `TerminalBackendRequest.backend_config`，记录 backend id、version、protocol version 和 mode。
- 指定 `terminal_backend_config` 但未配置 backend 时，`Executor` 会 fail closed，reason code 为 `terminal_backend_not_configured`。
- protocol version 不兼容时 backend 不会被调用。
- `backend_native_task` 默认被拒绝，除非后续有显式 policy gate。
- transcript / diff / changed files 这类 backend output 只能进入 artifact store，再通过 `ResourceRef` 进入 event；full content 不进入 event payload。
- `artifact_policy.capture` 不允许的 output kind 会 fail closed，且不会写 partial artifact。
- `artifact_policy` 要求 full content 进入 event 或 read model 时，会在调用 runner 前 fail closed。
- `TerminalBackendRunResult.backend_summary` 只包含 backend id、version、protocol version、mode、status 和 reason code。
- `action.completed` 和 `RunState.actions` 投影低敏 `terminal_backend` summary，但不包含 backend session id、本机路径、环境变量或完整输出。

仍未实现：

- 真实 terminal / PTY。
- 把 Codex / opencode / Claude 当作 terminal 后端。
- real sandbox / container。
- streaming product API。
- real HTTP terminal route。

## Goal

后续系统终端能力应该长成这样：

```text
Isotope approved action
  -> compatibility runner request
  -> system terminal / process runtime
  -> compatibility runner result
  -> Isotope artifact + canonical events + read model
```

关键原则：

- runner 负责“怎么跑”：terminal、PTY、sandbox、process lifecycle、streaming、cancel。
- Isotope 负责“能不能跑、怎么记录”：policy、approval、workspace grants、artifact、event、checkpoint、replay。
- runner 不能自己扩大权限，也不能绕过 Isotope 直接把完整输出塞进 event 或 read model。

## Contract Objects

### `TerminalBackendRequest`

这是 Isotope 交给 runner 的请求。它只能从已经批准的 action / decision 派生。

必需字段：

- `run_id`
- `proposal_id`
- `decision_id`
- `execution_id`
- `policy_profile_id`
- `policy_version`
- `registry_id`
- `registry_version`
- `grants`
- `workspace_binding`
- `command_request`
- `budget`
- `artifact_policy`
- `basis_event_ids`

`grants` 必须来自 `PolicyDecision.grants` snapshot。runner 返回的任何 grants 都不可信。

`workspace_binding` 必须来自 Isotope 已投影的 workspace binding / lease；不能让 runner 用裸路径自己决定工作目录。

`command_request` 后续可以有不同 shape，但 first implementation gate 只允许两类设计：

- `exec_argv`：结构化 argv，不是 shell string。
- `backend_native_task`：runner 自己的任务请求；该模式必须另有 policy profile，不得复用普通 command allowlist 偷开。

`artifact_policy` 说明哪些输出必须变成 artifact，例如 stdout、stderr、transcript、diff、changed files。默认 full content 不进 event / read model。

### `TerminalBackendResult`

这是 runner 返回给 adapter 的结果。它必须是 summary + output artifacts / artifact refs 形态；adapter 再把 output artifacts 写入 Isotope artifact store，生成 structured `ResourceRef`。

必需字段：

- `backend_session_id`
- `status`
- `started_at`
- `finished_at`
- `summary`
- `output_artifacts`
- `artifact_refs`
- `exit_code`
- `reason_code`
- `retryable`
- `resource_usage`

`status` 只允许：

- `completed`
- `failed`
- `cancelled`
- `timeout`

`summary` 必须低敏，适合进入 read model。它可以说“执行了什么、是否成功、结果在哪里”，不能包含完整 stdout、stderr、transcript 或文件内容。

`output_artifacts` 是 runner 给 adapter 的内容包，adapter 会写入 artifact store。`artifact_refs` 只允许指向 Isotope 已创建或接受的 structured `ResourceRef`；runner 不能用任意 path 或 URL 冒充 artifact。

### `TerminalBackendFailure`

失败也必须结构化。建议 stable reason codes：

- `terminal_backend_not_configured`
- `terminal_backend_request_denied`
- `terminal_backend_workspace_denied`
- `terminal_backend_start_failed`
- `terminal_backend_timeout`
- `terminal_backend_cancelled`
- `terminal_backend_protocol_error`
- `terminal_backend_output_too_large`
- `terminal_backend_artifact_write_failed`

裸异常文本只能进 debug log 或低敏 details，不能成为接口合同本身。

## Runtime Flow

1. App / agent 提交 action intent。
2. Isotope 编译成 `ActionProposal`。
3. `PolicyEngine` 产生 `PolicyDecision`。
4. 若需要 approval，先走 existing approval pause / resume。
5. 只有 approved / granted path 才能构造 `TerminalBackendRequest`。
6. Adapter 调真实 runner。
7. runner 返回 `TerminalBackendResult` 或 `TerminalBackendFailure`。
8. Isotope 把输出写入 artifact store，生成 `ResourceRef`。
9. Isotope 追加 canonical events，并投影低敏 read model。
10. Replay / checkpoint 只能依赖 canonical events、artifact metadata 和 `ResourceRef`，不能依赖 runner 临时状态。

## Hard Invariants

- Denied action must not call runner。
- Pending approval must not call runner。
- Forged approval grants must not affect backend request。
- Backend cannot invent or widen grants。
- Backend cannot choose workspace root from raw user input。
- Backend cannot write full stdout / stderr / transcript into event payload。
- Backend cannot write full content into `RunState.actions`。
- Backend cannot return unstructured artifact refs。
- Unknown backend status fails closed。
- Unsupported backend protocol version fails closed。
- Cancel / timeout / supersede must leave canonical linkage in Isotope。

## Streaming Boundary

真实 runner 可以支持 streaming output，但 Isotope first adapter 不应把 streaming 直接暴露为 product API。

允许的 first-slice shape：

- runner 可以产生 chunks。
- Adapter 把 chunks 汇总到 artifact content。
- Event / read model 只记录 summary、chunk count、truncated flag 和 artifact ref。

暂不包含：

- SSE / WebSocket。
- product terminal live UI。
- raw stream event log。
- terminal transcript 直接进 read model。

## Cancellation Boundary

Cancel 由 Isotope 发起，不由 runner 自行修改 run state。

建议流程：

1. Isotope 收到 cancel request，记录 canonical cancel request。
2. Adapter 把 cancel signal 发给 runner，并带上 basis ids。
3. runner 返回 cancel acknowledged / failed summary。
4. Isotope 追加 canonical cancellation outcome event。

如果 runner 已经 completed，Isotope 必须保留 completed history，不能把旧 execution 原地改成 cancelled。

## First Red Tests Recommendation

当前 first green slice 已覆盖这些 fake-backend tests：

1. Approved decision can create a `TerminalBackendRequest` with exact `PolicyDecision.grants` snapshot。
2. Denied decision does not call backend。
3. Pending approval does not call backend。
4. Backend result creates artifact refs and safe read-model summary without stdout / stderr full content。
5. Backend-provided forged grants are ignored or rejected。
6. Backend-provided raw file path artifact ref is rejected。
7. Unknown backend status fails closed with structured error。
8. Cancel request calls backend cancel path and preserves canonical basis linkage。

Executor integration green slice 还覆盖：

9. Configured fake backend is called through `Executor` and receives action-started basis linkage。
10. Backend protocol error becomes structured `action.failed` with no artifact side effect。
11. Backend-reported failure becomes structured `action.failed` with stable reason code。
12. Backend completed-without-output fails closed。
13. `InProcessServer(..., terminal_backend=...)` routes `submit_action(... terminal_exec ...)` to the configured backend。

这些 green slices 使用 fake / in-memory runner only。它们证明 runner contract 和 Isotope 外层接线路径，不证明 Codex / opencode / Claude integration。

## Non-Goals

本合同不包含：

- 选择具体 runner。
- 接 Codex / opencode / Claude。
- 启动真实 terminal / PTY。
- 开放 arbitrary shell。
- 实现 sandbox / container。
- 实现 git worktree executor。
- product terminal UI。
- real HTTP route。
- multi-user auth。
- public SDK。

## Stop Conditions

如果下一步需要以下任一项，应暂停并重新做 design：

- 必须现在选 runner 产品。
- 必须开放 shell string。
- 必须让 runner 直接读写任意 path。
- 必须把完整 transcript 放进 event / read model。
- 必须新增 dependency。
- 必须改变 event store append-only 语义。
- 必须进入 real concurrency / process supervisor。
