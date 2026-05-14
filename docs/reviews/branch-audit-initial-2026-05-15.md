# 分支初审：2026-05-15

状态：`初审完成`

## 审计边界

- 基准：当前 `main` 提交 `f4fcfc9`。
- 方式：只读检查 `git fetch --all --prune`、分支差异、提交主题和 worktree 状态。
- 不合并、不删除、不重写任何分支。
- 当前主工作区有文档整备改动，分支对比按 Git 提交图计算，不按未提交文件计算。

## 总体判断

现有分支不是同等优先级的多条产品线。

主要分成四类：

- `controlled-terminal-exec`：最大、最接近 AI 应用核心能力的分支。
- `agent-loop` 系列：一条逐步叠加的链，很多早期分支已被后续分支覆盖。
- `codex/spike-aggressive-dev`：激进应用探索快照，适合抽取思路和少量代码。
- `spike/app-agent-loop-friction`：相对 `main` 无差异，可视为已吸收或无待合并内容。

## 分支矩阵

| 分支 | 差异规模 | 主要内容 | 初步建议 |
| --- | ---: | --- | --- |
| `feature/controlled-terminal-exec` | 85 commits，19 src，32 tests | 终端执行、Codex CLI、LLM 工具调用、产品聊天入口 | 最高优先级深审；不要整分支合并，拆成应用能力切片 |
| `codex/spike-aggressive-dev` | 30 commits，5 src，14 tests | capability hub、LLM capability routing、自演化探索、大量 aggressive 文档 | 作为参考分支；先抽能力清单，不直接合并 |
| `spike/aggressive-dev` | 本地 ahead 1 / upstream behind 18 | 旧 aggressive 快照 | 基本被 `codex/spike-aggressive-dev` 取代，暂不处理 |
| `feature/agent-loop-tick-budget-read-model-spike` | 15 commits，7 src，16 tests | agent loop 链的最完整 tip，含 tick policy / tick budget | 若保留 agent loop，优先看这个 tip，早期链路分支不用逐个合 |
| `feature/agent-loop-tick-budget-pause-contract-review` | 14 commits | 上一条链的文档边界版本 | 被 read-model tip 覆盖，保留为参考 |
| `feature/agent-loop-tick-policy-demo-trace` | 13 commits | tick policy 演示 trace | 被后续 tick budget 分支覆盖 |
| `feature/agent-loop-tick-policy-read-model` | 12 commits | tick policy read model | 被后续 tick budget 分支覆盖 |
| `feature/agent-loop-tick-policy-boundary-review` | 11 commits | tick policy 边界文档 | 被后续 tick policy / budget 分支覆盖 |
| `feature/real-planner-adapter-contract-spike` | 10 commits | real planner adapter contract | 被 tick 系列后续分支包含 |
| `feature/real-planner-adapter-boundary-review` | 9 commits | real planner adapter 边界 | 被后续 contract / tick 分支包含 |
| `feature/agent-loop-demo-coverage-review` | 8 commits | demo coverage 评审 | 被后续分支包含，保留文档参考即可 |
| `feature/planner-restart-resume-demo-trace` | 7 commits | planner restart / resume trace | 被后续分支包含 |
| `feature/planner-approval-resume-demo-trace` | 6 commits | approval / resume trace | 被后续分支包含 |
| `feature/planner-step-demo-trace` | 5 commits | planner step demo trace | 被后续分支包含 |
| `feature/planner-step-driver-adapter` | 4 commits | planner step adapter | 被后续分支包含 |
| `feature/agent-loop-step-driver-restart` | 3 commits | step driver restart | 被后续分支包含 |
| `feature/agent-loop-step-driver` | 2 commits | step driver | 被后续分支包含 |
| `feature/agent-loop-run-control` | 1 commit | run control read model | 被后续分支包含 |
| `spike/app-agent-loop-friction` | 0 commits / 0 files | 相对 `main` 无差异 | 可列入待归档或待删除候选，删除前再确认远端策略 |

## 可合并代码来源

初步看，正经代码集中在三处：

1. `feature/controlled-terminal-exec`
   - `src/isotope_kernel/terminal*.py`
   - `src/isotope_kernel/codex_*.py`
   - `src/isotope_kernel/llm_*.py`
   - `src/isotope_kernel/model_tool_bridge.py`
   - 对应 `tests/isotope_kernel/test_*terminal*`、`test_*codex*`、`test_*llm*`

2. `feature/agent-loop-tick-budget-read-model-spike`
   - `src/isotope_kernel/agent_loop_control.py`
   - `src/isotope_kernel/agent_loop_step.py`
   - `src/isotope_kernel/agent_loop_planner_adapter.py`
   - `src/isotope_kernel/real_planner_adapter_contract.py`

3. `codex/spike-aggressive-dev`
   - `src/isotope_kernel/capability_hub.py`
   - `src/isotope_kernel/llm_provider.py`
   - `src/isotope_kernel/self_evolution.py`
   - 对应 capability / provider / self-evolution 测试

这些代码仍在旧 `src/isotope_kernel/` 命名下。
如果后续主线走 AI 应用结构，应优先移植到新目录设计，而不是照搬旧包名。

## 下一步建议

先固定当前文档整备结果，再深审 `feature/controlled-terminal-exec`。

深审目标不是“能不能整体合并”，而是拆出第一批应用能力：

- 终端执行后端。
- LLM 工具调用桥。
- Codex CLI / 任务执行适配。
- 产品聊天入口里真正可复用的部分。

深审后再决定哪些代码迁移到 `apps/`、`src/agents/`、`src/models/`、`src/features/`。
