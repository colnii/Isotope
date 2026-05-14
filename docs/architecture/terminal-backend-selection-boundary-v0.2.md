# Terminal Backend Selection Boundary v0.2

状态：`historical compatibility doc / superseded terminology`

Terminology correction: this file name is historical. The current source of truth is [Terminal Capacity / System Runner Boundary v0.2](terminal-capacity-system-runner-boundary-v0.2.md). Read "backend" in this document as terminal capacity runner / execution substrate. `terminal` is a capacity, system terminal is the runner, and Codex is reference code / optional code-writing tool work rather than Isotope's terminal backend.

本文原本回答下一步怎么选真实 terminal backend。纠偏后的当前读法更窄：Isotope 不继续手搓 terminal；后续应接系统终端 runner，并由 Isotope 包一层约束。当前仍不接任何真实系统终端 runner；selector / config first green slice 证明 runner 身份、版本、未配置失败和 runner-native task gate；artifact-policy first green slice 证明 transcript / diff / changed files 只能以 artifact + ref 形式回到事件；low-sensitive summary first green slice 证明 event / read model 可展示低敏摘要但不泄露路径、环境变量、session id 或完整输出。

## Plain-Language Summary

外行可以这样理解：

- 系统终端 runner 像“真正干活的师傅”，会打开终端、跑命令、处理进程和输出。
- Isotope 像“门卫和账本”，先判断这件事能不能做，再把能做的范围写清楚，最后记录做了什么、结果在哪里。
- 现在已经有门卫和账本的接口；下一步不是让 Isotope 自己学会当师傅，而是接系统终端 runner，并规定它必须从门卫那里拿任务、把结果交回账本。

## Implementation Status

当前 first green slice 包含：

- `TerminalBackendConfig`
- `TerminalBackendNotConfiguredError`
- `TerminalBackendRequest.backend_config`
- `default_terminal_backend_config()`
- `Executor(..., terminal_backend_config=...)`
- `InProcessServer(..., terminal_backend_config=...)`
- `TerminalBackendRunResult.backend_summary`
- `tests/isotope/test_terminal_backend_selector_config.py`
- `tests/isotope/test_terminal_backend_artifact_policy.py`

已验证：

- configured fake backend request 会携带 backend id、version、protocol version、mode 和 `allow_backend_native_task` 状态。
- 指定 `terminal_backend_config` 但没有配置 backend 时，`Executor` fail closed，追加 structured `action.failed`，reason code 是 `terminal_backend_not_configured`。
- backend protocol version 不兼容时，backend 不会被调用，且失败不产生 artifact side effect。
- `backend_native_task` 默认必须拒绝，除非后续单独打开 policy gate。
- backend 返回 transcript / diff / changed files 时，adapter 只写 artifact store，event 只出现 structured `ResourceRef` 和 summary，不包含 full content。
- `artifact_policy.capture` 不允许的输出类型会 fail closed，不写 partial artifact。
- `artifact_policy` 要求 full content 进入 event 或 read model 时，会在 backend 调用前 fail closed。
- `action.completed` / `RunState.actions` 可显示低敏 `terminal_backend` summary：backend id、version、protocol version、mode、status 和 reason code。
- 低敏 summary 不包含 backend session id、本机路径、环境变量、API key 或完整输出。

仍未实现：

- 真实 Codex / opencode / Claude adapter。
- backend 发现、安装或启动。
- interactive PTY / streaming product API。
- sandbox / container / git worktree executor。

## Current Decision

当前主线只接受这类 terminal capacity runner 方向：

```text
Isotope action / policy / approval / grants
  -> system terminal runner contract
  -> local system terminal / process runtime
  -> artifact refs + low-sensitive summary
  -> canonical events + read model + replay
```

系统终端 runner 必须被 Isotope 包起来，不能直接绕过 Isotope 写 event、read model 或 artifact full content。Codex / opencode / Claude-style 工具不自动成为 terminal capacity 的后端；Codex 只作为参考代码和可选代码开发工具。

## Candidate Approaches

### A. System terminal runner through Isotope contract

这是推荐方向。系统终端 runner 负责 terminal / process / sandbox / streaming / cancel。Isotope 只把 approved request、grants、workspace binding 和 artifact policy 交过去。

优点：

- 能复用成熟工具的真实执行能力。
- 不逼 Isotope 自研 PTY、sandbox、process supervisor。
- 更符合用户提出的“真实终端外面套 Isotope 约束”。

代价：

- 需要后续明确一个具体 runner 的启动方式、输入格式、输出格式和失败格式。
- 需要额外处理 runner 版本差异和本机配置缺失。

### B. Raw subprocess / PTY runner inside Isotope

不作为主线方向。它看起来短期快，但会把 Isotope 推向自研 terminal 产品：要处理交互、权限、进程树、环境、文件变更、streaming、cancel 和安全边界。

当前只保留 `ControlledTerminalRunner` 作为 deterministic boundary sample，不继续扩大成通用终端。

### C. Remote / container / git worktree executor

暂缓。这些能力以后可能需要，但它们同时打开 workspace isolation、network、cleanup、auth、cost 和安全策略问题。没有 concrete application friction 前不进入主线。

## Runner Contract Gate

接真实系统终端 runner 前，必须先有这些测试和文档结论：

1. **Runner not configured fail closed**：没有配置真实 runner 时，不应偷偷退回任意 shell 或更宽权限。
2. **Runner request is grants-bound**：runner 收到的 request 只能来自 `PolicyDecision.grants`、workspace binding 和 approved action。
3. **Runner native task is separately gated**：如果 runner 接收自然语言任务或自己的 task 格式，必须走单独 policy profile，不能复用普通 `terminal_exec` allowlist 偷开。
4. **Output returns as artifacts**：stdout、stderr、transcript、diff、changed files 只能进入 artifact store，再以 structured `ResourceRef` 进入事件。
5. **Events stay low-sensitive**：event / read model 只记录 summary、status、reason code、artifact refs 和 basis ids，不记录完整输出。
6. **Runner failure is structured**：启动失败、超时、权限拒绝、输出过大、协议不兼容都要变成 stable reason code。
7. **Cancel / timeout leave linkage**：取消或超时不能原地改历史，必须留下 canonical linkage。

## Minimal Red Tests

本 slice 已写 fake runner tests，不接真实系统终端 runner：

1. `Executor` 配置一个 runner selector 时，会把 runner identity / version 写入 request。
2. 未配置 selector 但要求 real runner mode 时，必须 `action.failed`，reason code 为 `terminal_backend_not_configured`。
3. `backend_native_task` 没有专门 policy profile 时必须拒绝，且不调用 runner。
4. runner 版本不兼容时 fail closed，并且没有 artifact side effect。
5. runner 返回 transcript / diff / changed files 时，adapter 只创建 artifacts 和 refs，不把 full content 放进 event。
6. `artifact_policy.capture` 不允许某类输出时，adapter fail closed，且不写 partial artifact。
7. `artifact_policy` 要求 full content 进 event / read model 时，request 阶段 fail closed，且不调用 runner。
8. selector/config 信息进入低敏 `action.completed` / read model summary，但不泄露真实本机路径、环境变量、runner session id 或完整输出。

这些 tests 的目的不是证明 Codex / opencode / Claude 已接好，而是证明 Isotope 外层不会被真实 runner 绕开。

## Implementation Order

建议顺序：

1. 写 fake runner selector / config 的 red tests：已完成。
2. 做最小 selector object，只表达 runner id、runner version、mode 和是否 configured：已完成。
3. 保持真实 runner disabled；用 fake runner 模拟 compatible / incompatible / missing / failed 几种结果：部分完成，missing / incompatible 已覆盖。
4. 写 fake runner artifact-policy tests，覆盖 transcript / diff / changed files artifact handoff 和 no full-content events：已完成。
5. 写 fake runner low-sensitive summary tests，覆盖 event / read model summary 且不泄露本机细节：已完成。
6. 文档和 demo 只说明“runner hook exists”，不宣称 real terminal 已可用。
7. 只有用户明确要求后，才进入真实系统终端 runner spike。Codex 仍只作为参考代码或可选代码开发工具。

## Non-Goals

本阶段不包含：

- 选择或安装真实 runner。
- 调用 Codex / opencode / Claude。
- 打开 arbitrary shell。
- 实现 interactive PTY。
- 实现 sandbox / container / git worktree executor。
- 实现 product terminal UI 或 HTTP terminal route。
- 引入新 dependency。
- 宣称当前终端能力是完整安全沙箱。

## Stop Conditions

出现以下情况必须暂停：

- 需要选具体真实 runner 产品。
- 需要新增 dependency。
- 需要让 runner 直接读写任意 path。
- 需要把完整输出、transcript 或 diff 放进 event / read model。
- 需要开放 broad write-capable command allowlist。
- 需要 real sandbox / container / git worktree / remote executor。
- 需要 product UI / auth / multi-user policy。
- 需要修改 event store append-only 语义。

## Relationship To Existing Docs

- [Real Terminal Backend Boundary](real-terminal-backend-boundary-v0.2.md) 说明为什么不继续手搓 terminal。
- [Terminal Backend Adapter Contract](terminal-backend-adapter-contract-v0.2.md) 说明 request / result / artifact / error 的接口合同。
- 本文只补上“接真实系统终端 runner 前如何选择和分阶段”的边界。
