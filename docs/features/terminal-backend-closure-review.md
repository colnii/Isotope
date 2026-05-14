# Terminal Backend Closure Review

状态：`historical compatibility review / superseded terminology`

Terminology correction: this file name is historical. The current source of truth is [Terminal Capacity / System Runner Boundary v0.2](../architecture/terminal-capacity-system-runner-boundary-v0.2.md). Read "backend" here as terminal capacity runner / execution substrate. `terminal` is a capacity, system terminal is the runner, and Codex is reference code / optional code-writing tool work rather than Isotope's terminal backend.

本文记录原 Terminal Backend 方向的 closure review。纠偏后的当前读法是：这轮终端能力已经收口到“fake runner contract + Isotope 外层约束”的边界，同时避免把 fake runner / boundary sample 误写成真实 Codex、opencode 或 Claude terminal 集成。

## 1. Scope Reviewed

本轮 review 覆盖：

- `terminal_exec` controlled terminal execution boundary sample。
- Historical Real Terminal Backend architecture correction。
- `TerminalBackendAdapter` request / result / failure contract。
- `Executor(..., terminal_backend=...)` 和 `InProcessServer(..., terminal_backend=...)` fake-backend wiring。
- `TerminalBackendConfig` selector / config boundary。
- backend artifact-policy handoff。
- low-sensitive backend summary projection。

本轮不评审真实系统终端 runner，也不实现真实 terminal / PTY / sandbox / process runtime。

## 2. Closure Judgment

Historical Terminal Backend first slice 可以标为 `first slice complete / closed for now`，但当前应读成 terminal capacity runner compatibility slice。

理由：

- 终端方向已经从“继续扩 `ControlledTerminalRunner`”纠偏为“terminal capacity 调用系统终端 runner + Isotope 外层约束”。
- Isotope 当前只负责 action、policy、approval、workspace/resource grants、artifact / `ResourceRef`、event log、read model、checkpoint 和 replay。
- Fake backend 已能通过 adapter contract 跑通 request、result、artifact refs、failure、cancel basis linkage 和 safe summary。
- Selector/config 已能把 backend identity、version、protocol 和 mode 放进 request，并在 backend 缺失、protocol 不兼容或 `backend_native_task` 默认未开放时 fail closed。
- Artifact-policy 已固定：transcript / diff / changed files 等完整内容只能进 artifact，不进 event / read model；full-content-in-event/read-model policy 会在 backend 调用前被拒绝。
- Low-sensitive backend summary 已投影到 `action.completed.terminal_backend` 和 `RunState.actions[*].terminal_backend`，只包含 backend id/version/protocol/mode/status/reason code，不暴露本机路径、env、backend session id 或完整输出。

这足够关闭当前 mainline kernel slice。下一步是否接系统终端 runner 是新的 implementation spike，不应由当前闭环 review 自动开始。

## 3. Verified Contracts

当前已固定的 contracts：

- Denied / pending action 不调用 backend。
- Backend request 只携带 policy-approved grants snapshot，不接受伪造 grants 提权。
- Raw local path ref 被拒绝，artifact handoff 必须使用 structured `ResourceRef`。
- Unknown backend status、backend-reported failure、completed-without-output 和 incompatible protocol 都进入 controlled failure path。
- Capture policy 拒绝时不写 partial artifact。
- Event / read model 只记录低敏 summary 和 artifact refs，不记录 stdout / stderr / transcript / diff / changed-files full content。
- 默认 `terminal_exec` path 仍可走原 controlled runner；选择 compatibility runner path 时，缺 runner 会 fail closed。
- Cancel path 当前只固定 request / basis linkage boundary，不代表真实 process kill。

## 4. Boundary Confirmations

仍未实现，且不应从本 slice 偷偷打开：

- 把 Codex / opencode / Claude 当作 terminal 后端。
- Interactive shell / PTY。
- Streaming output。
- Real sandbox / container / chroot。
- Git worktree executor。
- Remote executor。
- Network command surface。
- Product HTTP terminal route。
- Auth / multi-user terminal policy。
- Public SDK。
- 新 dependency。

Kernel 语义也未被扩大：

- Event store append-only 语义不变。
- Executor grants 语义不变。
- Artifact full content 不进入 native `RunState`。
- Projector 仍只从 canonical events 构建 read model。
- HTTP full-content route 和 real HTTP server 仍 deferred / not enabled。

## 5. Evidence

Implementation evidence:

- `src/isotope_kernel/terminal.py`
- `src/isotope_kernel/terminal_backend.py`
- `src/isotope_kernel/executor.py`
- `src/isotope_kernel/server.py`
- `src/isotope_kernel/projector.py`

Test evidence:

- `tests/isotope_kernel/test_terminal_tool_boundary.py`
- `tests/isotope_kernel/test_terminal_backend_adapter_contract.py`
- `tests/isotope_kernel/test_terminal_backend_executor_integration.py`
- `tests/isotope_kernel/test_terminal_backend_selector_config.py`
- `tests/isotope_kernel/test_terminal_backend_artifact_policy.py`

Docs evidence:

- `../architecture/controlled-terminal-execution-boundary-v0.2.md`
- `../architecture/real-terminal-backend-boundary-v0.2.md`
- `../architecture/terminal-backend-adapter-contract-v0.2.md`
- `../architecture/terminal-backend-selection-boundary-v0.2.md`

Current queue baseline before this docs-only review: `1090 passed`.

Post-closure addendum:

- Model Tool Catalog first slice now exposes `terminal_exec` as model-facing callable metadata through `InProcessServer.get_model_tool_catalog(...)`.
- This does not reopen the terminal capacity runner closure: the catalog is read-only metadata, preserves argv-only / allowlist / approval / artifact constraints, and does not call a real runner.
- `codex_task` is recorded as deferred / not callable until a separate Codex-as-tool boundary exists.
- Focused full regression baseline after this addendum, before the later Codex-as-tool Boundary slice: `1093 passed`.

## 6. Remaining Friction / Deferred Work

这些不是当前 slice 的 blocker：

- 选择真实系统终端 runner。
- Runner discovery / install / start / health check。
- 把真实 runner 的 session / run / task 概念映射到兼容 `TerminalBackendRequest` / `TerminalBackendRunResult`。
- Streaming / incremental artifact capture。
- Real cancel / process kill。
- Workspace path / mutation / diff policy。
- Auth、multi-user、audit retention 和 product UI。
- Public API / SDK。

## 7. Reopen Conditions

只有出现以下条件之一，才建议重新打开 terminal capacity runner implementation：

- 用户明确要求接系统终端 runner 或要求做 adapter spike。
- Application-layer prototype 或 external review 证明当前 request / artifact / summary contract 不够用。
- 安全 review 需要新增明确的 capture policy、workspace policy 或 runner health contract。
- 真实 runner 的 streaming / cancel / workspace behavior 需要进入 kernel boundary，而不是只停留在 app shell。

## 8. Next Suggested Path

默认下一步：停止 kernel expansion，等待系统终端 runner 需求、application-layer friction 或 external review feedback。

如果用户明确要继续接真实终端，下一批应先写 system terminal runner design / red tests，再实现最小 runner contract。不要在没有 runner 边界的情况下继续扩大 allowlist、打开 arbitrary shell、实现 PTY、接 container / git worktree、加 product terminal route 或新增依赖。
