# Agent 任务队列

状态：`当前入口 / 下一步目录结构设计`

## 当前事实

- Isotope 是 AI 应用软件，不是单纯内核项目。
- 本地只保留 `main`，远端只保留 `origin/main`。
- 旧功能分支已完成审计、代码抽取和清理。
- 可迁移代码已进入主线，剩余分支内容只保留历史参考价值。
- `docs/` 已分成 `current/`、`architecture/`、`features/`、`reviews/`、`archive/`。
- 应用目录结构还没有最终定稿，不在本批次移动代码。

## 已完成批次

1. 协作入口清理：`AGENTS.md` 已改成中文主叙述，并控制在 100 行以内。
2. 文档分层整理：`docs/` 根目录没有 Markdown 残留，入口集中到 `docs/current/`。
3. 术语索引：保留英文定位词，补中文解释和主要位置。
4. 应用目录方案：已写 [application-structure-plan](./application-structure-plan.md)。
5. 分支审计清理：结果见 [branch-cleanup](../reviews/branch-cleanup-2026-05-15.md)。
6. 文档二次清理：当前入口已刷新，不再传播旧分支暂停口径。

## 最近完成：文档二次清理

完成内容：

- 刷新当前入口文档里的阶段状态。
- 删除或改写已完成批次留下的“下一步迁移”“分支暂停”口径。
- 保留历史评审和归档，不批量改写审计证据。
- 不做代码目录迁移。

验收：

- `docs/current/` 能说明当前真实状态。
- `README.md` 不再要求继续暂停旧功能分支。
- `AGENTS.md` 不写临时分支规则。
- Markdown 相对链接无断链。

## 下一批次：目录结构与包名迁移

目标：

- 确定 `src/isotope/` 作为长期 Python 包命名空间。
- 建立服务近期迁移的目录骨架。
- 尽快把 `src/isotope_kernel/` 迁到新目录。
- 迁移时保留短期兼容层，避免一次性破坏已有命令和测试。
- 迁移完成后再恢复多分支并行开发。

初始参考：

- `apps/cli/`：命令行入口。
- `apps/api/`：后端入口。
- `src/isotope/assistant/`：产品助手入口。
- `src/isotope/features/`：聊天、项目助手、文件助手等可用功能。
- `src/isotope/capabilities/`：工具、技能、能力注册。
- `src/isotope/execution/`：shell、python、浏览器、沙箱执行。
- `src/isotope/workspace/`：文件、项目、git 工作区。
- `src/isotope/memory/`：记忆、检索、上下文。
- `src/isotope/policy/`：权限、审批、风险。
- `src/isotope/platform/`：事件、schema、registry、lifecycle。

## 验证命令

文档批次至少运行：

```bash
git diff --check
wc -l AGENTS.md
find docs -maxdepth 1 -type f -name '*.md' -print
```

代码未改时，不必运行完整测试。
