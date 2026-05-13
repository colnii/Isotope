# Terminal Capacity / System Runner Boundary v0.2

状态：`terminology correction / docs-only`

本文是当前终端方向的准绳：`terminal` 是 Isotope 的一个 capacity（能力），不是架构里的“后端”。系统终端只是这个 capacity 调用本机执行环境的 runner（执行器），它必须被 Isotope 的 action、policy、approval、workspace/resource grants、artifact、event、checkpoint 和 replay 边界包住。

旧文档和代码里仍保留 `TerminalBackend*` 名称，是历史兼容名。阅读这些名字时，应把它理解成 terminal capacity 的 runner / execution substrate（执行基座）合同，不要把它理解成 Isotope 之外的高层后端。

## Current Decision

- `terminal_exec` 是 model / app 可以请求的一项受控执行能力；`submit_model_tool_call(...)` 现在可把模型选择的 structured argv 转交给既有 `submit_action(...)`。
- `llm-terminal-tool-loop` demo 现在单独展示 terminal capacity：fake provider 只看见 `terminal_exec`，Isotope 通过 `submit_action(...)` 执行，tool-result message 只回传 status / execution id / artifact ref；它不使用 Codex 或 `codex_task`。
- 系统终端 runner 负责在本机执行已经批准的命令或任务。
- Isotope 负责判断能不能执行、执行范围多大、结果怎么交回、哪些内容只能进 artifact。
- Codex 不是 Isotope 的 terminal 后端，也不是 Isotope 的唯一执行候选；Codex 只作为参考代码，以及某些代码开发场景下的可选工具。
- opencode / Claude-style 工具也不自动成为 terminal capacity 的主线方向；后续是否接入，要由具体 friction 或用户明确选择触发。

## First Implementation Direction

下一步若继续接系统终端，应从 Linux 非交互系统终端 runner 开始：

1. 参考 Codex 的 shell / process / policy 代码，学习成熟执行器如何处理 argv、cwd、env、timeout、输出截断和失败。
2. 保持 Isotope 的外层约束：只接受 approved action、只使用 `PolicyDecision.grants`、只把 stdout / stderr / transcript / diff 等完整内容写入 artifact。
3. 保持默认 fail closed：未配置、未批准、超预算、输出策略不允许、返回格式不可信时，都不要偷偷退回任意 shell。
4. 先不做 interactive PTY、开放 shell、streaming product API、container、git worktree executor、remote executor 或 product terminal route。

## Compatibility Notes

- `docs/real-terminal-backend-boundary-v0.2.md`、`docs/terminal-backend-adapter-contract-v0.2.md`、`docs/terminal-backend-selection-boundary-v0.2.md` 和 `docs/terminal-backend-closure-review.md` 是历史锚点，文件名暂不迁移。
- `src/isotope_kernel/terminal_backend.py` 和 `TerminalBackend*` 类型名目前也是兼容名。未来如果重命名，需要单独做迁移计划和测试，不在本 docs-only 修正里完成。
- 任何未来实现都应把“系统终端”当作 terminal capacity 的 runner，而不是提高成 Isotope 的产品后端。
