# 分支审计刷新：2026-05-15

状态：`刷新完成`

## 本次检查

- 已运行 `git fetch --all --prune`。
- 基准：当前 `main` 提交 `27b5b44`。
- 范围：本地分支、远端分支、worktree 绑定、相对 `main` 的差异。
- 结论：除新建的本地迁移分支外，没有发现新的未知远端功能分支。

## 当前分支分组

| 分组 | 分支 | 当前判断 |
| --- | --- | --- |
| 终端迁移 | `feature/app-terminal-exec-migration` | 正在处理，已有 2 个提交，可继续小步收敛 |
| 终端原分支 | `feature/controlled-terminal-exec` | 仍是重要来源，但不能整分支合并 |
| 激进开发 | `codex/spike-aggressive-dev` | 新的有效激进分支，适合后续深审 |
| 旧激进快照 | `spike/aggressive-dev` | 旧自动化快照，已落后，不应优先处理 |
| agent-loop 链 | `feature/agent-loop-tick-budget-read-model-spike` 等 | 层叠分支，应看链尾，不逐个合 |
| 已无差异 | `spike/app-agent-loop-friction` | 相对当前 `main` 没有差异，可列入归档候选 |

## 数量概览

相对当前 `main`：

- `feature/app-terminal-exec-migration`：2 commits，13 files。
- `feature/controlled-terminal-exec`：85 commits，76 files。
- `codex/spike-aggressive-dev`：30 commits，75 files。
- `spike/aggressive-dev`：1 local commit，但远端比本地更新；不作为有效主线。
- `feature/agent-loop-tick-budget-read-model-spike`：15 commits，47 files。
- `spike/app-agent-loop-friction`：0 commits，0 files。

## 合并顺序建议

1. 先完成 `feature/app-terminal-exec-migration`。
   - 只收终端能力闭环。
   - 不继续扩展目录设计。
   - 完成后再合回 `main`。

2. 再深审 `codex/spike-aggressive-dev`。
   - 重点看 `capability_hub.py`、`self_evolution.py`、`llm_provider.py`。
   - 不直接合旧 `docs/aggressive/`。
   - 只抽可形成产品能力的代码。

3. 再看 agent-loop 链尾。
   - 优先看 `feature/agent-loop-tick-budget-read-model-spike`。
   - 早期 agent-loop 分支只作历史参考。

## 当前注意点

- `codex/spike-aggressive-dev` 和 `spike/aggressive-dev` 不能混用。
- `feature/controlled-terminal-exec` 已经被拆出终端迁移分支，后续只继续抽剩余 LLM / Codex / chat 能力。
- 当前目录设计尚未最终确定，迁移时只建立必要落点，不扩大新目录承诺。
