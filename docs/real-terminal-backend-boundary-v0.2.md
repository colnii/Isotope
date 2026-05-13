# Real Terminal Backend Boundary v0.2

状态：`historical compatibility doc / superseded terminology`

Terminology correction: this file name is historical. The current source of truth is [Terminal Capacity / System Runner Boundary v0.2](./terminal-capacity-system-runner-boundary-v0.2.md). Read "backend" in this document as terminal capacity runner / execution substrate, not as a higher Isotope backend. `terminal` is a capacity; system terminal is the runner used by that capacity. Codex is reference code and an optional code-writing tool, not Isotope's terminal backend.

本文原本纠正 Controlled Terminal Execution first slice 之后的方向：Isotope 不应继续把 `ControlledTerminalRunner` 扩成自研完整终端。纠偏后的当前读法是：后续应接入系统终端 runner，并在外层套 Isotope 的约束、审批、事件记录、artifact handoff 和 replay 边界。

## Why This Exists

`terminal_exec` first slice 证明了一件事：终端类动作可以通过 Isotope 既有的 action chain、policy grants、approval pause / resume、artifact provenance、read model、checkpoint 和 replay 路径被审计。

它没有证明另一件事：Isotope 自己应该实现一个完整好用的 terminal、PTY、sandbox、git worktree executor 或 process supervisor。

后续不要沿着 “给 `terminal_exec` 加更多命令 / shell / streaming / PTY” 的方向自然扩展。那会把 Isotope 推向自研终端产品，既难用，也容易绕开成熟执行器已有的权限、沙箱和交互能力。

## Correct Direction

当前应读成这种目标形态：

```text
agent / app shell
  -> Isotope action + policy + approval + workspace/resource grants
  -> terminal capacity system runner
  -> local system terminal / process runtime
  -> Isotope artifact + event + read model + replay
```

系统终端 runner 负责：

- terminal / PTY / subprocess lifecycle。
- sandbox、权限提示、工作目录隔离和环境准备。
- streaming output、交互输入、进程终止和超时。
- 与本机执行环境的兼容。Codex / opencode / Claude-style 工具不自动成为本 capacity 的后端；Codex 只作为参考代码和可选代码开发工具。

Isotope 负责：

- action proposal、policy decision、approval pause / resume。
- workspace / resource grants，不让 runner 自己决定能访问什么。
- terminal session / command 的低敏 summary、basis refs 和 outcome 投影。
- stdout / stderr / transcript / file diff 等结果转成受控 artifact / `ResourceRef`。
- event log、checkpoint、replay、retry / cancel / supersede linkage。
- structured error taxonomy 和 audit trail。

runner 不能绕过 Isotope 直接把结果写进 read model，也不能直接读写 artifact full content 给上层 UI。

## What Current `terminal_exec` Remains

当前 `terminal_exec` 只保留为 deterministic boundary sample：

- 用极窄 allowlist 验证 terminal-like action 能进 canonical action chain。
- 验证 approval-required command profile 可以复用 existing approval boundary。
- 验证 terminal output 可以作为 artifact，而不是直接塞进 event / read model。
- 验证 demo / JSON / trace 不暴露 stdout / stderr full content。

它不是最终 terminal backend，不应继续被当作 “把 shell 能力做全” 的主线。

## Adapter Shape

后续如果实现真实系统终端 runner，先从 runner contract 开始，而不是扩大 `terminal_exec` allowlist。详细兼容合同见 [Terminal Backend Adapter Contract v0.2](./terminal-backend-adapter-contract-v0.2.md)。

建议输入：

- `run_id`、`action_id` / `proposal_id` / `decision_id`。
- approved `PolicyDecision.grants` snapshot。
- workspace binding / lease / root reference。
- argv 或 backend-native command request。
- approval token / policy profile basis。
- timeout、output budget、cancel / supersede basis。

建议输出：

- backend session id / execution id。
- started / completed / failed / cancelled summary。
- exit code / signal / timeout summary。
- artifact refs for stdout / stderr / transcript / changed files / diff。
- redacted log summary。
- structured error code and retryability。

硬约束：

- `PolicyDecision.grants` 是执行权限来源。
- backend output 只能通过 artifact / `ResourceRef` 或低敏 summary 回到 Isotope。
- full transcript / file content 不进入 event payload 或 action read model。
- cancellation / supersede 必须留下 canonical event linkage。
- backend failure 走 structured error taxonomy，不用裸异常文本做接口。

## Non-Goals

本阶段不包含：

- 在 kernel 内实现完整 terminal。
- 任意 shell string。
- interactive PTY 产品化。
- 自研 sandbox / container / chroot。
- git worktree executor。
- remote executor。
- real HTTP terminal route。
- multi-user auth / product terminal UI。
- broad write-capable command allowlist。

## Next Gate

下一步如果继续开发，应该是 red-tests 先验证 `TerminalBackend` adapter boundary：

1. Isotope 如何把已批准的 action 交给真实 runner。
2. runner 如何把结果、日志、diff 和错误交还给 Isotope。
3. 哪些字段能进 event / read model，哪些只能进 artifact。
4. cancel / timeout / approval / workspace grants 如何贯通。

停止条件：

- 需要现在选定具体 runner 产品。
- 需要开放任意 shell。
- 需要实现 sandbox / container。
- 需要 product terminal UI。
- 需要扩展成通用 process supervisor。

在这些问题没有明确前，不继续扩大 `ControlledTerminalRunner`。
