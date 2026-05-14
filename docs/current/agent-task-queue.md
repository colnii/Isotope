# Agent 任务队列

状态：`当前入口 / 下一步应用内分层`

## 当前事实

- Isotope 是 AI 应用软件，不是单纯内核项目。
- 本地只保留 `main`，远端只保留 `origin/main`。
- 旧功能分支已完成审计、代码抽取和清理。
- 可迁移代码已进入主线，剩余分支内容只保留历史参考价值。
- `docs/` 已分成 `current/`、`architecture/`、`features/`、`reviews/`、`archive/`。
- 主包已迁移到 `src/isotope/`，后续继续做应用内分层。

## 已完成批次

1. 协作入口清理：`AGENTS.md` 已改成中文主叙述，并控制在 100 行以内。
2. 文档分层整理：`docs/` 根目录没有 Markdown 残留，入口集中到 `docs/current/`。
3. 术语索引：保留英文定位词，补中文解释和主要位置。
4. 应用目录方案：已写 [application-structure-plan](./application-structure-plan.md)。
5. 分支审计清理：结果见 [branch-cleanup](../reviews/branch-cleanup-2026-05-15.md)。
6. 文档二次清理：当前入口已刷新，不再传播旧分支暂停口径。
7. 包名迁移：`src/isotope_kernel/` 已迁到 `src/isotope/`。
8. 应用内分层第一批：平台 schema、平台事件、能力目录已迁入子目录。
9. 聊天功能入口：产品聊天入口已迁入 `src/isotope/features/chat/`。
10. 助手循环入口：`agent_loop_*` 已迁入 `src/isotope/assistant/`。
11. 资源层入口：workspace、artifact、RAG、memory 边界已迁入对应目录。
12. 权限与注册表入口：policy、action registry、errors 已迁入新目录。
13. 执行器入口：executor 已迁入 `src/isotope/execution/`。

## 最近完成：执行器入口迁移

完成内容：

- 将 `executor.py` 迁入 `src/isotope/execution/executor.py`。
- 更新 `server.py` 的活跃导入路径。
- 保留 `isotope.executor` 兼容导出，方便历史测试和调用点逐步更新。

验收：

- 旧路径 `isotope.executor` 仍可导入。
- 新路径 `isotope.execution.executor` 可直接导入。
- executor、terminal backend、tool invocation 相关测试和全量测试通过。

## 下一批次：应用内分层迁移

目标：

- 保持 `src/isotope/` 作为长期 Python 包命名空间。
- 把当前平铺模块逐步迁入 `assistant/`、`features/`、`platform/` 等层级。
- 下一步迁移 HTTP/API 入口或剩余工具适配器，不恢复旧包名。
- 迁移完成后再恢复多分支并行开发。

初始参考：

- `apps/cli/`：命令行入口。
- `apps/api/`：后端入口。
- `src/isotope/assistant/`：产品助手入口。
- `src/isotope/features/`：聊天、项目助手、文件助手等可用功能。
- `src/isotope/capabilities/`：工具、技能、能力注册。
- `src/isotope/execution/`：shell、python、浏览器、沙箱执行。
- `src/isotope/workspace/`：文件、项目、git 工作区。
- `src/isotope/rag/`：接入、检索、索引。
- `src/isotope/memory/`：记忆、总结、上下文。
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
代码迁移批次需运行相关测试；共享路径迁移后跑全量测试。
